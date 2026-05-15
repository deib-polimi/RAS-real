"""Patched version of the SeBS web_server_graph_mst that READS the request
payload instead of using a hardcoded {'size': 25000}.

PROBLEM in the original (/usr/src/app/web_server_graph_mst.py):
   @app.post('/')
   def index():
       return graph_mst_function.handler(json_data["graph_mst"])   # ← always size=25000

CONSEQUENCE: any noise we apply to the request size client-side is silently
discarded by the server. Service time is constant regardless of payload size.
This invalidates all "drift via noise_scale" experiments on the local Docker.

FIX: parse `request.get_json()` and use that as input to the handler. Falls
back to the original hardcoded values if the body is missing/invalid (so the
server stays robust to bad clients).
"""
from flask import Flask, request
from gevent.pywsgi import WSGIServer

import benchmarks.scientific.graph_mst as graph_mst_function

app = Flask(__name__)

# Original hardcoded defaults — kept ONLY as fallback for malformed requests.
json_data = {
    'network': {'url': 'https://sample-videos.com/img/Sample-jpg-image-50kb.jpg'},
    'sleep': {'sleep': 1},
    'dynamic_html': {'username': 'dragonbanana', 'random_len': 80000},
    'thumbnailer': {'url': 'https://sample-videos.com/img/Sample-jpg-image-50kb.jpg', 'width': 10, 'height': 10,
                    'n': 30000},
    'video_processing': {
        'url': 'https://freetestdata.com/wp-content/uploads/2022/02/Free_Test_Data_1MB_MP4.mp4',
        'duration': 2},
    'compression': {'url': 'https://cdn.bestmovie.it/wp-content/uploads/2020/05/winnie-the-pooh-disney-plus-HP.jpg',
                    'compression_mode': 1000},
    'image_recognition': {'url': 'https://sample-videos.com/img/Sample-jpg-image-50kb.jpg'},
    'pagerank': {'size': 1500},
    'graph_mst': {'size': 25000},
    'graph_bfs': {'size': 30000},
}


@app.post('/')
def index():
    # >>> THE FIX <<<  read payload from request; fallback only if missing/invalid.
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or 'size' not in payload:
        payload = json_data["graph_mst"]
    return graph_mst_function.handler(payload)


@app.get('/health')
def health():
    return "ok"


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    print(path)
    print(request.__dict__)
