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


# ---------------------------------------------------------
#     GET ONHAND ENDPOINT (Styled exactly like getOrder)
# ---------------------------------------------------------
@app.route("/getOnhand", methods=["GET"])
def get_onhand():

    # Required params
    item_list = request.args.get("items")        # comma-separated list
    facility_code = request.args.get("facility") # facility code

    # Validation
    if not (item_list and facility_code):
        return jsonify({
            "status": "error",
            "message": "Missing required params: items, facility"
        })

    # WMS LGF URL
    api_url = f"{WMS_BASE_URL}/wms/lgfapi/v10/entity/inventory/"

    # Query params
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

        # No data found
        if response.status_code == 404:
            return jsonify({
                "status": "success",
                "noData": True,
                "rows": []
            })

        # Successful call
        if 200 <= response.status_code < 300:
            try:
                data = response.json()
            except Exception:
                return {
                    "status": "error",
                    "message": "WMS returned non-JSON"
                }

            return jsonify({
                "status": "success",
                "noData": False if data else True,
                "rows": data
            })

        # For all other HTTP errors
        return jsonify({
            "status": "error",
            "httpStatus": response.status_code,
            "body": response.text
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ---------------------------------------------------------
# LOCAL RUN
# ---------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
