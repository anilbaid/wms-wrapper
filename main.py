from flask import Flask, request, jsonify
import os
import requests
from requests.auth import HTTPBasicAuth

app = Flask(__name__)

# Read from Replit secrets
WMS_BASE_URL = os.getenv("WMS_BASE_URL")  # e.g. https://xxxxxx.oraclecloud.com
WMS_USER = os.getenv("WMS_USER")
WMS_PASSWORD = os.getenv("WMS_PASSWORD")

@app.route("/")
def health():
    return jsonify({"status": "ok", "message": "WMS GetOrder wrapper is running"}), 200


@app.route("/getOrder", methods=["GET"])
def get_order():
    """
    Wrapper for:
    wms/lgfapi/v10/entity/order_dtl/?order_id__req_ship_date__gte={from_date}
      &order_id__req_ship_date__lt={to_date}
      &order_id__facility_id__code={facility_code}
      &status_id=0
      &values_list=order_id,order_nbr,item_id,item_id__code,ord_qty
    """

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    facility_code = request.args.get("facility_code")

    if not (from_date and to_date and facility_code):
        return jsonify({
            "status": "error",
            "message": "Missing required parameters: from_date, to_date, facility_code"
        }), 200

    # Build WMS URL
    wms_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/order_dtl/"

    params = {
        "order_id__req_ship_date__gte": from_date,
        "order_id__req_ship_date__lt": to_date,
        "order_id__facility_id__code": facility_code,
        "status_id": 0,
        "values_list": "order_id,order_nbr,item_id,item_id__code,ord_qty"
    }

    try:
        resp = requests.get(
            wms_url,
            params=params,
            auth=HTTPBasicAuth(WMS_USER, WMS_PASSWORD),
            timeout=30
        )
    except Exception as e:
        # Network / DNS / timeout errors -> still HTTP 200 for AI Studio
        return jsonify({
            "status": "error",
            "noData": True,
            "message": "Failed to call WMS API",
            "details": str(e)
        }), 200

    # --- Handle 404 => treat as NO DATA ---
    if resp.status_code == 404:
        return jsonify({
            "status": "success",
            "noData": True,
            "rows": [],
            "message": "No orders found for given criteria"
        }), 200

    # --- Handle normal success (2xx) ---
    if 200 <= resp.status_code < 300:
        try:
            wms_data = resp.json()
        except ValueError:
            # WMS didn't send JSON
            return jsonify({
                "status": "error",
                "noData": True,
                "message": "WMS returned non-JSON response",
                "raw": resp.text
            }), 200

        # You can adjust this depending on actual WMS response structure
        return jsonify({
            "status": "success",
            "noData": (not bool(wms_data)),
            "rows": wms_data
        }), 200

    # --- All other HTTP codes -> error but still 200 for AI Studio ---
    return jsonify({
        "status": "error",
        "noData": True,
        "httpStatus": resp.status_code,
        "message": "WMS returned an error",
        "wmsBody": resp.text
    }), 200


if __name__ == "__main__":
    # Replit usually listens on port 8000
    app.run(host="0.0.0.0", port=8000)
