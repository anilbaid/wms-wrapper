from flask import Flask, request, jsonify
import os
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta

app = Flask(__name__)

# Load environment variables
WMS_BASE_URL = os.getenv("WMS_BASE_URL")
WMS_USER = os.getenv("WMS_USER")
WMS_PASSWORD = os.getenv("WMS_PASSWORD")


# ---------------------------------------------------------
# SAFE JSON PARSER (FINAL FIXED VERSION)
# ---------------------------------------------------------
def safe_wms_json(response):
    """
    Normalizes all Oracle WMS LGF API return formats:
      1) list of rows
      2) {"rows": [...]}
      3) {"results": [...], "result_count": X}
      4) single dict --> converted to list
      5) strings --> ignored
    """
    try:
        raw = response.json()
    except:
        print("⚠ JSON decode error")
        return []

    if isinstance(raw, str):
        print("⚠ WMS returned STRING → ignoring")
        return []

    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):

        # Oracle pagination style
        if "results" in raw and isinstance(raw["results"], list):
            return raw["results"]

        # older API style
        if "rows" in raw and isinstance(raw["rows"], list):
            return raw["rows"]

        # single-row dict
        return [raw]

    return []


# ---------------------------------------------------------
# DEBUG
# ---------------------------------------------------------
@app.route("/debug-env")
def debug_env():
    return {
        "WMS_BASE_URL": WMS_BASE_URL,
        "WMS_USER": WMS_USER,
        "WMS_PASSWORD": "******" if WMS_PASSWORD else None
    }


@app.route("/")
def home():
    return {"status": "ok", "message": "Wrapper running on Render!"}


# ---------------------------------------------------------
# GET ORDER
# ---------------------------------------------------------
@app.route("/getOrder", methods=["GET"])
def get_order():

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    facility_code = request.args.get("facility_code")

    if not (from_date and to_date and facility_code):
        return jsonify({"status": "error", "message": "Missing required params"})

    api_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/order_dtl/"
    params = {
        "order_id__req_ship_date__gte": from_date,
        "order_id__req_ship_date__lt": to_date,
        "order_id__facility_id__code": facility_code,
        "status_id": 0,
        "values_list": "order_id__order_nbr,item_id,item_id__code,ord_qty"
    }

    try:
        response = requests.get(api_url, params=params,
                                auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD), timeout=30)
        rows = safe_wms_json(response)
        return {"status": "success", "rows": rows, "noData": not bool(rows)}

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------
# GET ONHAND
# ---------------------------------------------------------
@app.route("/getOnhand", methods=["GET"])
def get_onhand():

    item_list = request.args.get("items")
    facility = request.args.get("facility")

    if not (item_list and facility):
        return {"status": "error", "message": "Missing required params"}

    api_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/inventory/"
    params = {
        "item_id__item_alternate_code__in": item_list,
        "container_id__curr_location_id__replenishment_zone_id__code": "PFACE",
        "facility_id__code": facility,
        "values_list": "item_id__item_alternate_code,curr_qty"
    }

    try:
        response = requests.get(api_url, params=params,
                                auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD), timeout=30)
        rows = safe_wms_json(response)
        return {"status": "success", "rows": rows, "noData": not bool(rows)}

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------
# EXISTING MOVE REQUEST
# ---------------------------------------------------------
@app.route("/existMoveReq", methods=["GET"])
def exist_move_req():

    item_list = request.args.get("items")
    facility = request.args.get("facility")

    if not (item_list and facility):
        return {"status": "error", "message": "Missing required params"}

    api_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/movement_request_dtl/"
    params = {
        "item_id__code__in": item_list,
        "dest_zone_id__code": "PFACE",
        "status_id__in": "0,10",
        "movement_req_id__facility_id__code": facility,
        "values_list": "item_id__code,req_qty"
    }

    try:
        response = requests.get(api_url, params=params,
                                auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD), timeout=30)
        rows = safe_wms_json(response)
        return {"status": "success", "rows": rows, "noData": not bool(rows)}

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------
# REPLENISHMENT SUMMARY (FIXED)
# ---------------------------------------------------------
@app.route("/replenSummary", methods=["GET"])
def replen_summary():

    days = request.args.get("days")
    facility = request.args.get("facility")

    if not (days and facility):
        return {"status": "error", "message": "Missing required params"}

    days = int(days)

    # ignore today → start tomorrow
    today = datetime.now().date()
    start_day = today + timedelta(days=1)

    from_date = start_day.strftime("%Y-%m-%d")
    to_date = (start_day + timedelta(days=days)).strftime("%Y-%m-%d")   # LT comparison

    # -------------------------------------------------
    # STEP 1: GET ORDERS
    # -------------------------------------------------
    order_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/order_dtl/"
    order_params = {
        "order_id__req_ship_date__gte": from_date,
        "order_id__req_ship_date__lt": to_date,
        "order_id__facility_id__code": facility,
        "status_id": 0,
        "values_list": "order_id__order_nbr,item_id,item_id__code,ord_qty"
    }

    order_res = requests.get(order_url, params=order_params,
                             auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD), timeout=30)
    order_rows = safe_wms_json(order_res)

    order_summary = {}
    for row in order_rows:
        item = row.get("item_id__code")
        if not item:
            continue
        qty = float(row.get("ord_qty", 0))
        order_summary[item] = order_summary.get(item, 0) + qty

    if not order_summary:
        return {"status": "success", "rows": []}

    item_list = ",".join(order_summary.keys())

    # -------------------------------------------------
    # STEP 2: GET ONHAND
    # -------------------------------------------------
    onhand_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/inventory/"
    oh_params = {
        "item_id__item_alternate_code__in": item_list,
        "container_id__curr_location_id__replenishment_zone_id__code": "PFACE",
        "facility_id__code": facility,
        "values_list": "item_id__item_alternate_code,curr_qty"
    }

    oh_res = requests.get(onhand_url, params=oh_params,
                          auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD), timeout=30)
    oh_rows = safe_wms_json(oh_res)

    onhand_summary = {row.get("item_id__item_alternate_code"): float(row.get("curr_qty", 0))
                      for row in oh_rows if row.get("item_id__item_alternate_code")}

    # -------------------------------------------------
    # STEP 3: GET MOVE REQUESTS
    # -------------------------------------------------
    mo_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/movement_request_dtl/"
    mo_params = {
        "item_id__code__in": item_list,
        "dest_zone_id__code": "PFACE",
        "status_id__in": "0,10",
        "movement_req_id__facility_id__code": facility,
        "values_list": "item_id__code,req_qty"
    }

    mo_res = requests.get(mo_url, params=mo_params,
                          auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD), timeout=30)
    mo_rows = safe_wms_json(mo_res)

    mo_summary = {}
    for row in mo_rows:
        item = row.get("item_id__code")
        qty = float(row.get("req_qty", 0))
        mo_summary[item] = mo_summary.get(item, 0) + qty

    # -------------------------------------------------
    # COMBINE FINAL RESULT
    # -------------------------------------------------
    final_rows = []
    for item, ord_qty in order_summary.items():
        final_rows.append({
            "item": item,
            "ordered_qty": ord_qty,
            "onhand_qty": onhand_summary.get(item, 0),
            "pending_mo_qty": mo_summary.get(item, 0)
        })

    return {
        "status": "success",
        "from_date": from_date,
        "to_date": to_date,
        "rows": sorted(final_rows, key=lambda x: x["item"])
    }
# ---------------------------------------------------------
# SHIPPING KPI (ENHANCED)
# ---------------------------------------------------------
@app.route("/shippingKPI", methods=["GET"])
def shipping_kpi():

    days = request.args.get("days")
    facility = request.args.get("facility")

    if not (days and facility):
        return {"status": "error", "message": "Missing required params"}

    try:
        days = int(days)
    except:
        return {"status": "error", "message": "Days must be numeric"}

    # ---------------------------------------------------
    # DATE RANGE
    # ---------------------------------------------------
    today = datetime.now()
    from_date = (today - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    to_date = today.strftime("%Y-%m-%dT23:59:59Z")

    # ---------------------------------------------------
    # API CALL
    # ---------------------------------------------------
    api_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/inventory_history/"
    params = {
        "create_ts__range": f"{from_date},{to_date}",
        "facility_id__code": facility,
        "history_activity_id": 3,      # Container shipped
        "company_id__code": "INTELLINUM2"
    }

    try:
        response = requests.get(
            api_url,
            params=params,
            auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD),
            timeout=30
        )
        rows = safe_wms_json(response)

    except Exception as e:
        return {"status": "error", "message": str(e)}

    # ---------------------------------------------------
    # KPI CALCULATIONS
    # ---------------------------------------------------
    total_units = 0
    unique_orders = set()
    unique_containers = set()

    for row in rows:

        # Units shipped = absolute value of adj_qty or units_shipped field
        try:
            shipped = float(row.get("units_shipped") or 0)
        except:
            shipped = 0

        total_units += shipped

        # Unique order count
        order_nbr = row.get("order_nbr")
        if order_nbr:
            unique_orders.add(order_nbr)

        # Unique container count
        container = row.get("container_nbr")
        if container:
            unique_containers.add(container)

    summary = {
        "total_units_shipped": total_units,
        "total_orders_shipped": len(unique_orders),
        "total_containers_shipped": len(unique_containers)
    }

    # ---------------------------------------------------
    # FINAL RESPONSE
    # ---------------------------------------------------
    return {
        "status": "success",
        "from_date": from_date,
        "to_date": to_date,
        "summary": summary
    }

@app.route("/receivingKPI", methods=["GET"])
def receiving_kpi():

    days = request.args.get("days")
    facility = request.args.get("facility")

    if not (days and facility):
        return {"status": "error", "message": "Missing required params"}

    try:
        days = int(days)
    except:
        return {"status": "error", "message": "Days must be numeric"}

    # ---------------------------------------------------
    # DATE RANGE
    # ---------------------------------------------------
    today = datetime.now()
    from_date = (today - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    to_date = today.strftime("%Y-%m-%dT23:59:59Z")

    # ---------------------------------------------------
    # API CALL
    # ---------------------------------------------------
    api_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/inventory_history/"
    params = {
        "create_ts__range": f"{from_date},{to_date}",
        "facility_id__code": facility,
        "history_activity_id": 1,      # Container received
        "company_id__code": "INTELLINUM2"
    }

    try:
        response = requests.get(
            api_url,
            params=params,
            auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD),
            timeout=30
        )
        rows = safe_wms_json(response)

    except Exception as e:
        return {"status": "error", "message": str(e)}

    # ---------------------------------------------------
    # KPI CALCULATIONS
    # ---------------------------------------------------
    total_units = 0
    unique_shipments = set()
    unique_containers = set()

    for row in rows:

        # Units shipped = absolute value of adj_qty or units_shipped field
        try:
            received = float(row.get("adj_qty") or 0)
        except:
            received = 0

        total_units += received

        # Unique order count
        shipment_nbr = row.get("shipment_nbr")
        if shipment_nbr:
            unique_shipments.add(shipment_nbr)

        # Unique container count
        container = row.get("container_nbr")
        if container:
            unique_containers.add(container)

    summary = {
        "total_units_received": total_units,
        "total_shipment_received": len(unique_shipments),
        "total_containers_received": len(unique_containers)
    }

    # ---------------------------------------------------
    # FINAL RESPONSE
    # ---------------------------------------------------
    return {
        "status": "success",
        "from_date": from_date,
        "to_date": to_date,
        "summary": summary
    }

#---Ontimereceiving---
# ---------------------------------------------------------
# ON-TIME RECEIVING KPI
# ---------------------------------------------------------
@app.route("/onTimeReceivingKPI", methods=["GET"])
def on_time_receiving_kpi():

    days = request.args.get("days")
    facility = request.args.get("facility")

    if not (days and facility):
        return {"status": "error", "message": "Missing required params"}

    try:
        days = int(days)
    except:
        return {"status": "error", "message": "Days must be numeric"}

    # DATE RANGE
    today = datetime.utcnow()
    from_dt = today - timedelta(days=days)
    from_date = from_dt.strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")

    # -------------------------------------------------
    # STEP 1: GET EXPECTED RECEIPT DATES (FROM PO HDR)
    # -------------------------------------------------
    po_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/purchase_order_hdr/"
    po_params = {
        "facility_id__code": facility,
        "delivery_date__range": f"{from_date},{to_date}",
        "company_id__code": "INTELLINUM2",
    }

    try:
        po_res = requests.get(po_url, params=po_params,
                              auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD), timeout=30)
        po_rows = safe_wms_json(po_res)
    except Exception as e:
        return {"status": "error", "message": f"PO API error: {e}"}

    expected_map = {}  # po_nbr → expected_delivery_ts

    for row in po_rows:
        po = row.get("po_nbr")
        delivery = row.get("delivery_date")

        if po and delivery:
            # Assume expected delivery by end of day 23:59:59
            expected_ts = f"{delivery}T23:59:59Z"
            expected_map[po] = expected_ts

    # If no POs found
    if not expected_map:
        return {
            "status": "success",
            "from_date": from_date,
            "to_date": to_date,
            "message": "No purchase orders found in date range",
            "summary": {},
            "rows": []
        }

    # -------------------------------------------------
    # STEP 2: GET ACTUAL RECEIPTS (INVENTORY HISTORY)
    # -------------------------------------------------
    ih_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/inventory_history/"
    ih_params = {
        "history_activity_id": 4,   # Container Received
        "facility_id__code": facility,
        "company_id__code": "INTELLINUM2",
        "create_ts__range": f"{from_date}T00:00:00Z,{to_date}T23:59:59Z"
    }

    try:
        ih_res = requests.get(ih_url, params=ih_params,
                              auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD), timeout=30)
        ih_rows = safe_wms_json(ih_res)
    except Exception as e:
        return {"status": "error", "message": f"Inventory history API error: {e}"}

    # -------------------------------------------------
    # STEP 3: MATCH ACTUAL vs EXPECTED
    # -------------------------------------------------
    total_receipts = 0
    on_time = 0
    late = 0

    detail_rows = []  # for optional display

    for row in ih_rows:
        po = row.get("po_nbr")
        actual_ts = row.get("create_ts")

        if not po or not actual_ts:
            continue

        if po not in expected_map:
            continue  # PO not in expected window

        expected_ts = expected_map[po]

        total_receipts += 1

        # Compare timestamps
        if actual_ts <= expected_ts:
            status = "ON_TIME"
            on_time += 1
        else:
            status = "LATE"
            late += 1

        detail_rows.append({
            "po_nbr": po,
            "expected_ts": expected_ts,
            "actual_ts": actual_ts,
            "status": status
        })

    # -------------------------------------------------
    # STEP 4: KPI SUMMARY
    # -------------------------------------------------
    summary = {
        "total_receipts": total_receipts,
        "on_time_receipts": on_time,
        "late_receipts": late,
        "on_time_percent": (on_time / total_receipts * 100) if total_receipts > 0 else 0
    }

    return {
        "status": "success",
        "from_date": from_date,
        "to_date": to_date,
        "summary": summary,
        "rows": detail_rows
    }
    
    
@app.route("/receivingKPI1", methods=["GET"])
def receiving_kpi1():

    days = request.args.get("days")
    facility = request.args.get("facility")

    if not (days and facility):
        return {"status": "error", "message": "Missing required params"}

    try:
        days = int(days)
    except:
        return {"status": "error", "message": "Days must be numeric"}

    # ---------------------------------------------------
    # DATE RANGE
    # ---------------------------------------------------
    today = datetime.now()
    from_date = (today - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    to_date = today.strftime("%Y-%m-%dT23:59:59Z")

    # Base API URL
    api_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/inventory_history/"

    # ---------------------------------------------------
    # ACTIVITY 1 — LPN RECEIVED DATA
    # ---------------------------------------------------
    params_act1 = {
        "create_ts__range": f"{from_date},{to_date}",
        "facility_id__code": facility,
        "history_activity_id": 1,   # LPN Received
        "company_id__code": "INTELLINUM2"
    }

    try:
        response = requests.get(
            api_url,
            params=params_act1,
            auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD),
            timeout=30
        )
        rows = safe_wms_json(response)
    except Exception as e:
        return {"status": "error", "message": str(e)}

    # ---------------------------------------------------
    # KPI CALCULATIONS FOR ACTIVITY 1
    # ---------------------------------------------------
    total_units = 0
    unique_shipments = set()
    unique_containers = set()

    # Shipment → {dock_time, lpns}
    shipment_lpn_map = {}

    for row in rows:
        # Units received
        try:
            received = float(row.get("adj_qty") or 0)
        except:
            received = 0
        total_units += received

        # Unique shipments
        shipment = row.get("shipment_nbr")
        if shipment:
            unique_shipments.add(shipment)

        # Unique LPNs (containers)
        lpn = row.get("container_nbr")
        if lpn:
            unique_containers.add(lpn)

        # Capture Dock Time (earliest activity 1 timestamp)
        if shipment and lpn:
            ts = row.get("create_ts")
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))

            if shipment not in shipment_lpn_map:
                shipment_lpn_map[shipment] = {
                    "dock_time": dt,
                    "lpns": set([lpn])
                }
            else:
                shipment_lpn_map[shipment]["dock_time"] = min(
                    shipment_lpn_map[shipment]["dock_time"], dt
                )
                shipment_lpn_map[shipment]["lpns"].add(lpn)

    # ---------------------------------------------------
    # ACTIVITY 51 — STOCK TIME LOOKUP (PUTAWAY COMPLETE)
    # ---------------------------------------------------
    dock_to_stock_minutes = []

    for shipment, data in shipment_lpn_map.items():
        lpns = list(data["lpns"])
        dock_time = data["dock_time"]
        if not lpns:
            continue

        # Prepare CSV for container_nbr__in
        lpn_csv = ",".join(lpns)

        params_act51 = {
            "create_ts__range": f"{from_date},{to_date}",
            "facility_id__code": facility,
            "history_activity_id": 51,  # Putaway / Stocked
            "company_id__code": "INTELLINUM2",
            "container_nbr__in": lpn_csv
        }

        try:
            act51_resp = requests.get(
                api_url,
                params=params_act51,
                auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD),
                timeout=30
            )
            act51_rows = safe_wms_json(act51_resp)
        except Exception:
            continue

        # Per-LPN earliest stock time
        lpn_stock_times = {}

        for r in act51_rows:
            lpn = r.get("container_nbr")
            ts = r.get("create_ts")
            if not (lpn and ts):
                continue

            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))

            if lpn not in lpn_stock_times:
                lpn_stock_times[lpn] = dt
            else:
                lpn_stock_times[lpn] = min(lpn_stock_times[lpn], dt)

        # Compute Dock-to-Stock time for each LPN
        for lpn, stock_time in lpn_stock_times.items():
            dts = (stock_time - dock_time).total_seconds() / 60
            if dts >= 0:
                dock_to_stock_minutes.append(dts)

    # Average DTS for the period
    avg_dts = (
        round(sum(dock_to_stock_minutes) / len(dock_to_stock_minutes), 2)
        if dock_to_stock_minutes else 0
    )

    # ---------------------------------------------------
    # FINAL SUMMARY
    # ---------------------------------------------------
    summary = {
        "total_units_received": total_units,
        "total_shipment_received": len(unique_shipments),
        "total_containers_received": len(unique_containers),
        "avg_dock_to_stock_minutes": avg_dts
    }

    # ---------------------------------------------------
    # FINAL RESPONSE
    # ---------------------------------------------------
    return {
        "status": "success",
        "from_date": from_date,
        "to_date": to_date,
        "summary": summary
    }


# ---------------------------------------------------------
# LOCAL RUN
# ---------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
