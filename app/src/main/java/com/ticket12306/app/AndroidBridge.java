package com.ticket12306.app;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.webkit.JavascriptInterface;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

public class AndroidBridge {

    private final Context context;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private volatile boolean grabRunning = false;
    private final List<String> grabLogs = new ArrayList<>();
    private boolean grabSuccess = false;
    private String grabError = "";

    public AndroidBridge(Context context) {
        this.context = context.getApplicationContext();
    }

    @JavascriptInterface
    public String queryTickets(String from, String to, String date) {
        try {
            return TrainApi.queryLeftTicket(context, from, to, date).toString();
        } catch (Exception e) {
            return "{\"success\":false,\"message\":\"" + escape(e.getMessage()) + "\"}";
        }
    }

    @JavascriptInterface
    public String checkLogin() {
        try {
            JSONObject o = new JSONObject();
            o.put("loggedIn", TrainApi.isLoggedIn(context));
            return o.toString();
        } catch (Exception e) {
            return "{\"loggedIn\":false}";
        }
    }

    @JavascriptInterface
    public void openLoginPage() {
        mainHandler.post(new Runnable() {
            @Override
            public void run() {
                if (context instanceof MainActivity) {
                    ((MainActivity) context).showLoginWebView();
                }
            }
        });
    }

    @JavascriptInterface
    public void logout() {
        TrainApi.clearCookies(context);
    }

    @JavascriptInterface
    public String getPassengers() {
        try {
            return TrainApi.getPassengers(context).toString();
        } catch (Exception e) {
            return "{\"success\":false,\"message\":\"" + escape(e.getMessage()) + "\"}";
        }
    }

    @JavascriptInterface
    public String startGrab(String trainCode, String from, String to,
                            String date, String seat, String passengersJson) {
        if (grabRunning) {
            return "{\"success\":false,\"message\":\"抢票已在运行中\"}";
        }
        if (!TrainApi.isLoggedIn(context)) {
            return "{\"success\":false,\"message\":\"请先登录12306账号\"}";
        }

        grabRunning = true;
        grabSuccess = false;
        grabError = "";
        grabLogs.clear();
        addLog("抢票启动: " + trainCode + " " + from + "→" + to + " " + date);

        JSONArray passengersArr;
        try {
            passengersArr = new JSONArray(passengersJson);
        } catch (Exception e) {
            passengersArr = new JSONArray();
        }
        final JSONArray passengers = passengersArr;

        final String fTrain = trainCode, fFrom = from, fTo = to, fDate = date, fSeat = seat;

        new Thread(new Runnable() {
            @Override
            public void run() {
                int attempts = 0;
                while (grabRunning && attempts < 300) {
                    attempts++;
                    addLog("第" + attempts + "次查询余票...");
                    try {
                        org.json.JSONObject result = TrainApi.queryLeftTicket(context, fFrom, fTo, fDate);
                        org.json.JSONArray trains = result.optJSONArray("trains");
                        boolean found = false;
                        if (trains != null) {
                            for (int i = 0; i < trains.length(); i++) {
                                org.json.JSONObject t = trains.getJSONObject(i);
                                if (t.optString("code").equalsIgnoreCase(fTrain)) {
                                    String seatText = t.optString("seatText", "");
                                    addLog(fTrain + " 余票: " + seatText);
                                    if (!seatText.contains("无票") && !seatText.isEmpty()) {
                                        found = true;
                                        addLog("✅ 发现有票，尝试提交订单...");
                                        if (passengers.length() > 0) {
                                            org.json.JSONObject orderResult = TrainApi.submitOrder(
                                                context, fTrain, fDate, fSeat, fFrom, fTo, passengers);
                                            boolean ok = orderResult.optBoolean("success", false);
                                            addLog("下单结果: " + orderResult.optString("message", ""));
                                            if (ok) {
                                                addLog("🎉🎉🎉 抢票成功！请尽快在12306 App中支付！");
                                                grabSuccess = true;
                                                grabRunning = false;
                                                return;
                                            }
                                        } else {
                                            addLog("⚠️ 有票但未选择乘车人，请先登录并选择乘车人");
                                        }
                                        break;
                                    }
                                }
                            }
                        }
                        if (!found) addLog("暂无票，3秒后重试...");
                    } catch (Exception e) {
                        addLog("查询异常: " + e.getMessage());
                    }
                    try { Thread.sleep(3000); } catch (InterruptedException e) { break; }
                }
                addLog(grabSuccess ? "✅ 抢票成功！" : "抢票任务结束");
                grabRunning = false;
            }
        }).start();

        return "{\"success\":true,\"message\":\"抢票已启动\"}";
    }

    @JavascriptInterface
    public void stopGrab() {
        grabRunning = false;
        addLog("用户手动停止");
    }

    @JavascriptInterface
    public String getGrabStatus() {
        try {
            JSONObject obj = new JSONObject();
            obj.put("running", grabRunning);
            obj.put("success", grabSuccess);
            obj.put("logs", new JSONArray(grabLogs));
            return obj.toString();
        } catch (Exception e) {
            return "{\"running\":false,\"logs\":[]}";
        }
    }

    @JavascriptInterface
    public void open12306App() {
        mainHandler.post(new Runnable() {
            @Override
            public void run() {
                try {
                    Intent intent = new Intent(Intent.ACTION_VIEW);
                    intent.setPackage("com.MobileTicket");
                    intent.setData(Uri.parse("mct12306://login"));
                    context.startActivity(intent);
                } catch (Exception e) {
                    try {
                        Intent market = new Intent(Intent.ACTION_VIEW);
                        market.setData(Uri.parse("market://details?id=com.MobileTicket"));
                        context.startActivity(market);
                    } catch (Exception e2) {
                        Intent web = new Intent(Intent.ACTION_VIEW);
                        web.setData(Uri.parse("https://www.12306.cn"));
                        context.startActivity(web);
                    }
                }
            }
        });
    }

    private void addLog(String msg) {
        String time = new SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(new Date());
        grabLogs.add("[" + time + "] " + msg);
    }

    private static String escape(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");
    }
}
