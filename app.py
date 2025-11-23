from flask import Flask, request, jsonify
import os

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "ok", "message": "wrapper running"}), 200
