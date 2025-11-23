from flask import Flask, request, jsonify
import os
import requests
from requests.auth import HTTPBasicAuth

app = Flask(__name__)

# Load environment variables from Render
WMS_BASE_URL = os.getenv("WMS_BASE_URL")
WMS_USER = os.getenv("WMS_USER")
WMS_PASSWORD = os.getenv("WMS_PASSWORD")

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


@app.route("/getOrder", methods=["GET"])
def get_order():

    # Read query parameters from URL
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    facility_code = request.args.get("facility_code")

    # Validate
    if not (from_date and to_date and facility_code):
        return jsonify({
            "status": "error",
            "message": "Missing required params: from_date, to_date, facility_code"
        })

    # WMS URL
    api_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/order_dtl/"

    # Query params needed by WMS
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
            return jsonify({
                "status": "success",
                "noData": True,
                "rows": []
            })

        if response.status_code >= 200 and response.status_code < 300:
            try:
                data = response.json()
            except Exception:
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
