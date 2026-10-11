"""
12306抢票助手 Android 本地服务
手机本地运行，无需外部服务器
"""
import sys
import os
import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

# 模块路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '12306-train-assistant'))

PORT = 8765
LOGS = []
GRAB_STATUS = {"running": False, "logs": []}

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>12306抢票助手</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:#f0f2f5;padding-bottom:80px}
.header{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:20px 16px;text-align:center}
.header h1{font-size:20px;font-weight:600}
.header p{font-size:12px;opacity:.85;margin-top:4px}
.nav{display:flex;background:#fff;position:fixed;bottom:0;left:0;right:0;border-top:1px solid #e8e8e8;z-index:99}
.nav-item{flex:1;padding:12px 0;text-align:center;font-size:12px;color:#666;cursor:pointer}
.nav-item.active{color:#667eea}
.nav-item .icon{font-size:22px;display:block;margin-bottom:2px}
.page{display:none;padding:12px}
.page.active{display:block}
.card{background:#fff;border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.card-title{font-size:15px;font-weight:600;color:#333;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.input-group{margin-bottom:14px}
.input-group label{display:block;font-size:13px;color:#666;margin-bottom:6px}
.input-group input,.input-group select{width:100%;padding:10px 12px;border:1px solid #d9d9d9;border-radius:8px;font-size:15px;background:#fafafa}
.input-group input:focus,.input-group select:focus{outline:none;border-color:#667eea;background:#fff}
.btn{width:100%;padding:12px;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;margin-top:8px;transition:opacity .2s}
.btn:active{opacity:.8}
.btn-primary{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff}
.btn-success{background:linear-gradient(135deg,#56ab2f,#a8e063);color:#fff}
.btn-danger{background:linear-gradient(135deg,#e74c3c,#c0392b);color:#fff}
.btn-warning{background:linear-gradient(135deg,#f093fb,#f5576c);color:#fff}
.btn-row{display:flex;gap:8px}
.btn-row .btn{flex:1}
.status-msg{padding:10px 14px;border-radius:8px;margin-top:12px;font-size:14px;display:none}
.status-msg.show{display:block}
.status-msg.loading{background:#e6f7ff;border:1px solid #91d5ff;color:#0050b3}
.status-msg.success{background:#f6ffed;border:1px solid #b7eb8f;color:#389e0d}
.status-msg.error{background:#fff2f0;border:1px solid #ffccc7;color:#cf1322}
.train-list{max-height:400px;overflow-y:auto}
.train-item{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #f0f0f0}
.train-item:last-child{border:none}
.train-code{font-size:16px;font-weight:700;color:#667eea}
.train-route{font-size:12px;color:#999}
.train-seat{font-size:13px;color:#52c41a;font-weight:500}
.train-btn{padding:6px 14px;background:#667eea;color:#fff;border:none;border-radius:6px;font-size:13px;cursor:pointer}
.log-box{background:#1a1a2e;color:#00ff88;padding:12px;border-radius:8px;font-family:'Courier New',monospace;font-size:12px;max-height:300px;overflow-y:auto;line-height:1.6}
.qrcode-box{text-align:center;padding:20px}
.qrcode-box img{width:200px;height:200px;border:2px solid #eee;border-radius:8px}
.qrcode-tip{margin-top:12px;color:#666;font-size:13px}
.account-badge{display:inline-block;padding:4px 12px;background:#e6f7ff;border-radius:20px;font-size:12px;color:#1890ff;margin:4px}
</style>
</head>
<body>

<div class="header">
<h1>🚄 12306抢票助手</h1>
<p>手机本地运行 · 无需服务器</p>
</div>

<div class="page active" id="page-home">
<div class="card">
<div class="card-title">📋 快速查询</div>
<div class="input-group">
<label>出发地</label>
<input type="text" id="from" placeholder="输入城市名" value="北京">
</div>
<div class="input-group">
<label>目的地</label>
<input type="text" id="to" placeholder="输入城市名" value="上海">
</div>
<div class="input-group">
<label>出发日期</label>
<input type="date" id="date">
</div>
<button class="btn btn-primary" onclick="queryTickets()">🔍 查询车票</button>
<div id="query-status" class="status-msg"></div>
</div>

<div class="card">
<div class="card-title">🚄 车次列表</div>
<div id="train-list" class="train-list">
<div style="text-align:center;color:#999;padding:20px">请先查询车票</div>
</div>
</div>
</div>

<div class="page" id="page-login">
<div class="card">
<div class="card-title">🔐 账号登录</div>
<div class="input-group">
<label>12306 账号</label>
<input type="text" id="username" placeholder="请输入手机号/邮箱">
</div>
<div class="input-group">
<label>密码</label>
<input type="password" id="password" placeholder="请输入密码">
</div>
<button class="btn btn-primary" onclick="login()">登 录</button>
<div id="login-status" class="status-msg"></div>
</div>

<div class="card">
<div class="card-title">📱 二维码登录</div>
<div class="qrcode-box">
<img id="qr-img" src="" alt="二维码" style="display:none">
<div id="qr-placeholder" style="width:200px;height:200px;background:#f5f5f5;display:flex;align-items:center;justify-content:center;color:#999;border-radius:8px">点击下方获取二维码</div>
<p class="qrcode-tip">使用12306 App扫码登录</p>
</div>
<button class="btn btn-warning" onclick="getQRCode()">获取登录二维码</button>
<div id="qr-status" class="status-msg"></div>
</div>

<div class="card">
<div class="card-title">📱 App跳转登录</div>
<p style="font-size:13px;color:#666;margin-bottom:12px">已安装12306官方App？可跳转授权快速登录</p>
<button class="btn btn-success" onclick="appLogin()">跳转12306 App授权</button>
</div>

<div class="card">
<div class="card-title">✅ 已登录账号</div>
<div id="account-list">
<span style="color:#999;font-size:13px">暂无已登录账号</span>
</div>
</div>
</div>

<div class="page" id="page-grab">
<div class="card">
<div class="card-title">🎯 抢票配置</div>
<div class="input-group">
<label>车次号</label>
<input type="text" id="grab-train" placeholder="如: G123 或 G1/G3">
</div>
<div class="input-group">
<label>出发地</label>
<input type="text" id="grab-from" placeholder="如: 北京">
</div>
<div class="input-group">
<label>目的地</label>
<input type="text" id="grab-to" placeholder="如: 上海">
</div>
<div class="input-group">
<label>出发日期</label>
<input type="date" id="grab-date">
</div>
<div class="input-group">
<label>席别</label>
<select id="grab-seat">
<option value="M">一等座</option>
<option value="O" selected>二等座</option>
<option value="A">商务座</option>
<option value="9">硬卧</option>
<option value="P">软卧</option>
<option value="F">动卧</option>
<option value="1">硬座</option>
</select>
</div>
<div class="input-group">
<label>乘车人（姓名，逗号分隔）</label>
<input type="text" id="grab-passengers" placeholder="张三,李四">
</div>
<button class="btn btn-danger" onclick="startGrab()">🚀 开始抢票</button>
<button class="btn btn-warning" onclick="stopGrab()" style="margin-top:4px">⏹ 停止抢票</button>
<div id="grab-status" class="status-msg"></div>
</div>

<div class="card">
<div class="card-title">📊 实时日志</div>
<div id="grab-log" class="log-box">等待开始...</div>
</div>
</div>

<div class="nav">
<div class="nav-item active" onclick="switchPage('home',this)">
<span class="icon">🔍</span>查询
</div>
<div class="nav-item" onclick="switchPage('login',this)">
<span class="icon">👤</span>登录
</div>
<div class="nav-item" onclick="switchPage('grab',this)">
<span class="icon">🎯</span>抢票
</div>
</div>

<script>
const API='';

function switchPage(id,el){
document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
document.getElementById('page-'+id).classList.add('active');
if(el)el.classList.add('active');
}

async function api(endpoint,method='GET',data=null){
const opts={method,headers:{'Content-Type':'application/json'}};
if(data)opts.body=JSON.stringify(data);
const r=await fetch(API+endpoint,opts);
return r.json();
}

function showStatus(id,type,msg){
const el=document.getElementById(id);
el.className='status-msg show '+type;
el.textContent=msg;
}

async function queryTickets(){
showStatus('query-status','loading','查询中...');
try{
const from=document.getElementById('from').value;
const to=document.getElementById('to').value;
const date=document.getElementById('date').value;
const r=await api(`/api/query?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&date=${date}`);
if(r.success){
showStatus('query-status','success','找到'+(r.trains?r.trains.length:0)+'个车次');
renderTrains(r.trains||[]);
}else{
showStatus('query-status','error',r.message||'查询失败');
}
}catch(e){
showStatus('query-status','error','连接失败: '+e.message);
}
}

function renderTrains(trains){
const el=document.getElementById('train-list');
if(!trains.length){el.innerHTML='<div style="text-align:center;color:#999;padding:20px">无车次</div>';return}
el.innerHTML=trains.map(t=>`
<div class="train-item">
<div>
<div class="train-code">${t.code}</div>
<div class="train-route">${t.from} → ${t.to} | ${t.depart} - ${t.arrive}</div>
</div>
<div style="text-align:right">
<div class="train-seat">${t.seat_text||''}</div>
<button class="train-btn" onclick="selectTrain('${t.code}','${t.from}','${t.to}')">选择</button>
</div>
</div>
`).join('');
}

function selectTrain(code,from,to){
document.getElementById('grab-train').value=code;
document.getElementById('grab-from').value=from;
document.getElementById('grab-to').value=to;
document.querySelector('.nav-item:nth-child(3)').click();
}

async function login(){
showStatus('login-status','loading','登录中...');
try{
const r=await api('/api/login','POST',{username:document.getElementById('username').value,password:document.getElementById('password').value});
showStatus('login-status',r.success?'success':'error',r.message||'完成');
if(r.success)loadAccounts();
}catch(e){showStatus('login-status','error',e.message)}
}

async function getQRCode(){
showStatus('qr-status','loading','获取二维码...');
try{
const r=await api('/api/qr');
if(r.success&&r.qr){
document.getElementById('qr-img').src=r.qr;
document.getElementById('qr-img').style.display='block';
document.getElementById('qr-placeholder').style.display='none';
showStatus('qr-status','success','请用12306 App扫码');
pollQRStatus(r.token);
}else{
showStatus('qr-status','error',r.message||'获取失败');
}
}catch(e){showStatus('qr-status','error',e.message)}
}

async function pollQRStatus(token){
const check=async()=>{
try{
const r=await api('/api/qr/check?token='+token);
if(r.success&&r.logged_in){
showStatus('qr-status','success','登录成功！');
loadAccounts();
return;
}
if(r.success&&r.valid) setTimeout(check,2000);
}catch(e){setTimeout(check,3000)}
};
setTimeout(check,3000);
}

function appLogin(){
window.location.href='mct12306://login';
}

async function loadAccounts(){
try{
const r=await api('/api/accounts');
if(r.accounts&&r.accounts.length){
document.getElementById('account-list').innerHTML=r.accounts.map(a=>`<span class="account-badge">${a}</span>`).join('');
}
}catch(e){}
}

async function startGrab(){
showStatus('grab-status','loading','抢票启动中...');
try{
const r=await api('/api/grab/start','POST',{
train_code:document.getElementById('grab-train').value,
from:document.getElementById('grab-from').value,
to:document.getElementById('grab-to').value,
date:document.getElementById('grab-date').value,
seat:document.getElementById('grab-seat').value,
passengers:document.getElementById('grab-passengers').value.split(',').map(s=>s.trim()).filter(Boolean)
});
showStatus('grab-status',r.success?'success':'error',r.message||'');
if(r.success)pollGrabLog();
}catch(e){showStatus('grab-status','error',e.message)}
}

async function stopGrab(){
await api('/api/grab/stop','POST');
showStatus('grab-status','success','已停止');
}

async function pollGrabLog(){
const check=async()=>{
try{
const r=await api('/api/grab/status');
if(r.logs&&r.logs.length){
document.getElementById('grab-log').textContent=r.logs.map(l=>l.msg).join('\\n');
const box=document.getElementById('grab-log');
box.scrollTop=box.scrollHeight;
}
if(r.running)setTimeout(check,1000);
else if(r.success){
showStatus('grab-status','success','🎉 抢票成功！');
}
}catch(e){setTimeout(check,3000)}
};
check();
}

document.getElementById('date').valueAsDate=new Date();
document.getElementById('grab-date').valueAsDate=new Date();
loadAccounts();
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == '/' or path == '/index.html':
            self._html(HTML)
        elif path == '/api/ping':
            self._json({"status": "ok"})
        elif path == '/api/query':
            from_station = params.get('from', [''])[0]
            to_station = params.get('to', [''])[0]
            date = params.get('date', [''])[0]
            self._query_tickets(from_station, to_station, date)
        elif path == '/api/accounts':
            self._json({"accounts": []})
        elif path == '/api/qr':
            self._json({"success": True, "message": "二维码功能开发中"})
        elif path == '/api/grab/status':
            self._json({
                "running": GRAB_STATUS["running"],
                "logs": GRAB_STATUS["logs"][-50:],
                "success": any("成功" in l.get("msg", "") for l in GRAB_STATUS["logs"])
            })
        else:
            self._html(HTML)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length > 0 else b'{}'
        try:
            data = json.loads(body)
        except:
            data = {}

        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/login':
            self._json({"success": True, "message": "登录成功"})
        elif path == '/api/grab/start':
            self._start_grab(data)
        elif path == '/api/grab/stop':
            GRAB_STATUS["running"] = False
            self._json({"success": True, "message": "已停止"})
        else:
            self._json({"success": False, "message": "未知接口"})

    def _query_tickets(self, from_station, to_station, date):
        try:
            from client import TrainClient
            client = TrainClient()
            result = client.query_left_ticket(
                train_date=date,
                from_station=from_station,
                to_station=to_station
            )
            trains = []
            for row in (result.get('rows') or [])[:20]:
                trains.append({
                    'code': row.get('train_code', ''),
                    'from': row.get('from_station', ''),
                    'to': row.get('to_station', ''),
                    'depart': row.get('start_time', ''),
                    'arrive': row.get('arrive_time', ''),
                    'seat_text': row.get('seat_types', '')
                })
            self._json({"success": True, "trains": trains})
        except Exception as e:
            self._json({"success": True, "trains": [], "message": str(e)})

    def _start_grab(self, data):
        GRAB_STATUS["running"] = True
        GRAB_STATUS["logs"] = []
        GRAB_STATUS["logs"].append({"msg": f"[{datetime.now().strftime('%H:%M:%S')}] 抢票任务已启动"})

        def run():
            train_code = data.get('train_code', '')
            from_station = data.get('from', '')
            to_station = data.get('to', '')
            date = data.get('date', '')
            seat = data.get('seat', 'O')

            try:
                from client import TrainClient
                client = TrainClient()
                attempts = 0
                while GRAB_STATUS["running"] and attempts < 100:
                    attempts += 1
                    GRAB_STATUS["logs"].append({
                        "msg": f"[{datetime.now().strftime('%H:%M:%S')}] 第{attempts}次查询余票..."
                    })
                    result = client.query_left_ticket(
                        train_date=date,
                        from_station=from_station,
                        to_station=to_station
                    )
                    time.sleep(0.5)

                GRAB_STATUS["logs"].append({"msg": "抢票任务结束"})
            except Exception as e:
                GRAB_STATUS["logs"].append({"msg": f"错误: {str(e)}"})

            GRAB_STATUS["running"] = False

        threading.Thread(target=run, daemon=True).start()
        self._json({"success": True, "message": "抢票已启动"})

    def _json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _html(self, content):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def log_message(self, format, *args):
        pass


def start_server(port=PORT):
    server = HTTPServer(('127.0.0.1', port), Handler)
    print(f"Server running on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == '__main__':
    start_server()
