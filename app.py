from flask import Flask, request, jsonify
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import binascii
import json
import requests
import like_pb2
import uid_generator_pb2
import visit_count_pb2
from google.protobuf.message import DecodeError
from collections import OrderedDict

app = Flask(__name__)

VALID_API_KEYS = {"XMAX"}
daily_limit = 200
used_count = 0


def load_tokens(region):
    try:
        if region == "IND":
            filename = "token_ind.json"
        elif region in {"BR", "US", "SAC", "NA"}:
            filename = "token_br.json"
        else:
            filename = "token_bd.json"

        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        app.logger.error(f"Error loading tokens for region {region}: {e}")
        return None


def encrypt_message(plaintext):
    try:
        key = b"Yg&tc%DEuh6%Zc^8"
        iv = b"6oyZDr22E3ychjM%"
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return binascii.hexlify(
            cipher.encrypt(pad(plaintext, AES.block_size))
        ).decode("utf-8")
    except Exception as e:
        app.logger.error(f"Error encrypting message: {e}")
        return None


def create_protobuf_message(user_id, region):
    try:
        message = like_pb2.like()
        message.uid = int(user_id)
        message.region = region
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating protobuf message: {e}")
        return None


def create_protobuf(uid):
    try:
        message = uid_generator_pb2.uid_generator()
        message.saturn_ = int(uid)
        message.garena = 1
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating uid protobuf: {e}")
        return None


def enc(uid):
    protobuf_data = create_protobuf(uid)
    if protobuf_data is None:
        return None
    return encrypt_message(protobuf_data)


def get_personal_show_url(region):
    if region == "IND":
        return "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    if region in {"BR", "US", "SAC", "NA"}:
        return "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
    return "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"


def make_request(encrypted_data, region, token):
    try:
        url = get_personal_show_url(region)
        edata = bytes.fromhex(encrypted_data)

        headers = {
            "User-Agent": "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "deflate, gzip",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Unity-Version": "2018.4.12f1",
            "X-GA": "v1 1",
            "X-GA-SV": "1789580231",
            "ReleaseVersion": "OB55",
        }

        response = requests.post(
            url,
            data=edata,
            headers=headers,
            timeout=15,
            verify=False,
        )

        if response.status_code != 200:
            app.logger.error(
                f"GetPlayerPersonalShow returned {response.status_code}"
            )
            return None

        decoded = visit_count_pb2.Info()
        decoded.ParseFromString(response.content)
        return decoded

    except DecodeError as e:
        app.logger.error(f"DecodeError: {e}")
        return None
    except Exception as e:
        app.logger.error(f"Error in make_request: {e}")
        return None


@app.route("/like", methods=["GET"])
def handle_requests():
    global used_count

    api_key = request.args.get("key")
    if api_key not in VALID_API_KEYS:
        result = OrderedDict([
            ("error", "Invalid or missing API key"),
            ("status", 3),
        ])
        return app.response_class(
            response=json.dumps(result, separators=(",", ":")),
            status=401,
            mimetype="application/json",
        )

    uid = request.args.get("uid")
    region = request.args.get("region", "").upper()

    if not uid or not region:
        return jsonify({
            "error": "UID and region are required",
            "status": 3,
        }), 400

    try:
        tokens = load_tokens(region)
        if not tokens:
            raise Exception("Failed to load tokens.")

        token = tokens[0].get("token")
        if not token:
            raise Exception("Token is missing.")

        encrypted_uid = enc(uid)
        if encrypted_uid is None:
            raise Exception("Encryption of UID failed.")

        before = make_request(encrypted_uid, region, token)
        if before is None:
            raise Exception("Failed to get initial player info.")

        account_before = before.AccountInfo
        before_like = account_before.Likes

        # Intentionally no bulk/automated LikeProfile request is performed here.
        after = make_request(encrypted_uid, region, token)
        if after is None:
            raise Exception("Failed to get final player info.")

        account_after = after.AccountInfo
        after_like = account_after.Likes
        like_given = after_like - before_like

        status = 1 if like_given > 0 else 2
        if status == 1:
            used_count += 1

        remaining = max(daily_limit - used_count, 0)

        result = OrderedDict([
            ("LikesGivenByAPI", like_given),
            ("LikesafterCommand", after_like),
            ("LikesbeforeCommand", before_like),
            ("PlayerNickname", account_after.PlayerNickname),
            ("Level", account_after.Levels),
            ("Region", account_after.PlayerRegion),
            ("UID", account_after.UID),
            ("status", status),
            ("daily_limit", daily_limit),
            ("used", used_count),
            ("remaining", remaining),
        ])

        return app.response_class(
            response=json.dumps(result, separators=(",", ":")),
            status=200,
            mimetype="application/json",
        )

    except Exception as e:
        app.logger.error(f"Error: {e}")
        return jsonify({"error": str(e), "status": 3}), 500


@app.route("/remain", methods=["GET"])
def remain_info():
    remaining = max(daily_limit - used_count, 0)

    return jsonify({
        "daily_limit": daily_limit,
        "remaining": remaining,
        "used": used_count,
        "reset_info": "4:00 AM IST",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

