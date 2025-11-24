from flask import Flask, request, jsonify
import os
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta

app = Flask(__name__)

# Load environment variables from Render
WMS_BASE_URL = os.getenv("WMS_BASE_URL")
WMS_USER = os.getenv("WMS_USER")
WMS_PASSWORD = os.getenv("WMS_PASSWORD")


# ---------------------------------------------------------
# DEBUG ENV ENDPOINT
# ---------------------------------------------------------
@app.route("/debug-env")
def debug_env():
    return {
        "WMS_BASE_URL": os.getenv("WMS_BASE_URL"),
        "WMS_USER": os.getenv("WMS_USER"),
        "WMS_PASSWORD": "******" if os.getenv("WMS_PASSWORD") else None
    }


@app.route("/")
def home():
    return {"status": "ok", "message": "Wrapper running on Render!"}


# ---------------------------------------------------------
# GET ORDER ENDPOINT
# ---------------------------------------------------------
@app.route("/getOrder", methods=["GET"])
def get_order():

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    facility_code = request.args.get("facility_code")

    if not (from_date and to_date and facility_code):
        return jsonify({
            "status": "error",
            "message": "Missing required params: from_date, to_date, facility_code"
        })

    api_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/order_dtl/"

    params = {
        "order_id__req_ship_date__gte": from_date,
        "order_id__req_ship_date__lt": to_date,
        "order_id__facility_id__code": facility_code,
        "status_id": 0,
        "values_list": "order_id__order_nbr,item_id,item_id__code,ord_qty"
    }

    try:
        response = requests.get(
            api_url,
            params=params,
            auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD),
            timeout=30
        )

        if response.status_code == 404:
            return jsonify({"status": "success", "noData": True, "rows": []})

        if 200 <= response.status_code < 300:
            try:
                data = response.json()
            except:
                return {"status": "error", "message": "WMS returned non-JSON"}

            return jsonify({
                "status": "success",
                "noData": False if data else True,
                "rows": data
            })

        return jsonify({
            "status": "error",
            "httpStatus": response.status_code,
            "body": response.text
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ---------------------------------------------------------
# GET ONHAND ENDPOINT
# ---------------------------------------------------------
@app.route("/getOnhand", methods=["GET"])
def get_onhand():

    item_list = request.args.get("items")
    facility_code = request.args.get("facility")

    if not (item_list and facility_code):
        return jsonify({
            "status": "error",
            "message": "Missing required params: items, facility"
        })

    api_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/inventory/"

    params = {
        "item_id__item_alternate_code__in": item_list,
        "container_id__curr_location_id__replenishment_zone_id__code": "PFACE",
        "facility_id__code": facility_code,
        "values_list": "item_id__item_alternate_code,curr_qty"
    }

    try:
        response = requests.get(
            api_url,
            params=params,
            auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD),
            timeout=30
        )

        if response.status_code == 404:
            return jsonify({"status": "success", "noData": True, "rows": []})

        if 200 <= response.status_code < 300:
            try:
                data = response.json()
            except:
                return {"status": "error", "message": "WMS returned non-JSON"}

            return jsonify({
                "status": "success",
                "noData": False if data else True,
                "rows": data
            })

        return jsonify({
            "status": "error",
            "httpStatus": response.status_code,
            "body": response.text
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ---------------------------------------------------------
# EXIST MOVE REQUEST ENDPOINT
# ---------------------------------------------------------
@app.route("/existMoveReq", methods=["GET"])
def exist_move_req():

    item_list = request.args.get("items")
    facility_code = request.args.get("facility")

    if not (item_list and facility_code):
        return jsonify({
            "status": "error",
            "message": "Missing required params: items, facility"
        })

    api_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/movement_request_dtl/"

    params = {
        "item_id__code__in": item_list,
        "dest_zone_id__code": "PFACE",
        "status_id__in": "0,10",
        "movement_req_id__facility_id__code": facility_code,
        "values_list": "item_id__code,req_qty"
    }

    try:
        response = requests.get(
            api_url,
            params=params,
            auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD),
            timeout=30
        )

        if response.status_code == 404:
            return jsonify({"status": "success", "noData": True, "rows": []})

        if 200 <= response.status_code < 300:
            try:
                data = response.json()
            except:
                return {"status": "error", "message": "WMS returned non-JSON"}

            return jsonify({
                "status": "success",
                "noData": False if data else True,
                "rows": data
            })

        return jsonify({
            "status": "error",
            "httpStatus": response.status_code,
            "body": response.text
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ---------------------------------------------------------
# NEW COMBINED ENDPOINT
# ---------------------------------------------------------
@app.route("/replenSummary", methods=["GET"])
def replen_summary():

    days = request.args.get("days")
    facility_code = request.args.get("facility")

    if not (days and facility_code):
        return jsonify({"status": "error", "message": "Missing required params: days, facility"})

    try:
        days = int(days)
    except:
        return jsonify({"status": "error", "message": "days must be a number"})

    # Calculate date range
    today = datetime.now().date()
    from_date = today.strftime("%Y-%m-%d")
    to_date = (today + timedelta(days=days)).strftime("%Y-%m-%d")

    # ------------------------------
    # STEP 1 — GET ORDER DATA
    # ------------------------------
    order_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/order_dtl/"
    order_params = {
        "order_id__req_ship_date__gte": from_date,
        "order_id__req_ship_date__lt": to_date,
        "order_id__facility_id__code": facility_code,
        "status_id": 0,
        "values_list": "order_id__order_nbr,item_id,item_id__code,ord_qty"
    }

    try:
        order_res = requests.get(order_url, params=order_params,
                                 auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD), timeout=30)
        order_rows = order_res.json() if order_res.status_code == 200 else []
    except:
        return jsonify({"status": "error", "message": "Error calling getOrder"})

    # Aggregate ordered qty per item
    order_summary = {}
    for row in order_rows:
        item = row.get("item_id__code")
        qty = float(row.get("ord_qty", 0))
        order_summary[item] = order_summary.get(item, 0) + qty

    # No orders? return empty
    if not order_summary:
        return jsonify({"status": "success", "rows": []})

    # Create CSV for WMS queries
    item_csv = ",".join(order_summary.keys())

    # ------------------------------
    # STEP 2 — GET ONHAND
    # ------------------------------
    onhand_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/inventory/"
    onhand_params = {
        "item_id__item_alternate_code__in": item_csv,
        "container_id__curr_location_id__replenishment_zone_id__code": "PFACE",
        "facility_id__code": facility_code,
        "values_list": "item_id__item_alternate_code,curr_qty"
    }

    onhand_summary = {}
    try:
        oh_res = requests.get(onhand_url, params=onhand_params,
                              auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD), timeout=30)
        oh_rows = oh_res.json() if oh_res.status_code == 200 else []

        for row in oh_rows:
            item = row.get("item_id__item_alternate_code")
            qty = float(row.get("curr_qty", 0))
            onhand_summary[item] = qty

    except:
        return jsonify({"status": "error", "message": "Error calling getOnhand"})

    # ------------------------------
    # STEP 3 — GET EXISTING MOVE REQUESTS
    # ------------------------------
    mo_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/movement_request_dtl/"
    mo_params = {
        "item_id__code__in": item_csv,
        "dest_zone_id__code": "PFACE",
        "status_id__in": "0,10",
        "movement_req_id__facility_id__code": facility_code,
        "values_list": "item_id__code,req_qty"
    }

    mo_summary = {}
    try:
        mo_res = requests.get(mo_url, params=mo_params,
                              auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD), timeout=30)
        mo_rows = mo_res.json() if mo_res.status_code == 200 else []

        for row in mo_rows:
            item = row.get("item_id__code")
            qty = float(row.get("req_qty", 0))
            mo_summary[item] = mo_summary.get(item, 0) + qty

    except:
        return jsonify({"status": "error", "message": "Error calling existMoveReq"})

    # ------------------------------
    # STEP 4 — BUILD FINAL RESPONSE
    # ------------------------------
    final_rows = []

    for item, ord_qty in order_summary.items():
        final_rows.append({
            "item": item,
            "ordered_qty": ord_qty,
            "onhand_qty": onhand_summary.get(item, 0),
            "pending_mo_qty": mo_summary.get(item, 0)
        })

    # Sort output by item for consistency
    final_rows = sorted(final_rows, key=lambda x: x["item"])

    return jsonify({
        "status": "success",
        "from_date": from_date,
        "to_date": to_date,
        "facility": facility_code,
        "rows": final_rows
    })


# ---------------------------------------------------------
# LOCAL RUN
# ---------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
