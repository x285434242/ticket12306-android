package com.ticket12306.app;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.webkit.JavascriptInterface;

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

    private static final String TICKET12306_PACKAGE = "com.MobileTicket";

    public AndroidBridge(Context context) {
        this.context = context;
    }

    @JavascriptInterface
    public String queryTickets(final String from, final String to, final String date) {
        try {
            return TrainApi.queryLeftTicket(from, to, date).toString();
        } catch (Exception e) {
            try {
                return new JSONObject().put("success", false).put("message", e.getMessage()).toString();
            } catch (Exception e2) {
                return "{\"success\":false,\"message\":\"unknown error\"}";
            }
        }
    }

    @JavascriptInterface
    public void open12306App() {
        mainHandler.post(new Runnable() {
            @Override
            public void run() {
                try {
                    Intent intent = new Intent(Intent.ACTION_VIEW);
                    intent.setPackage(TICKET12306_PACKAGE);
                    intent.setData(Uri.parse("mct12306://login"));
                    context.startActivity(intent);
                } catch (Exception e) {
                    try {
                        Intent market = new Intent(Intent.ACTION_VIEW);
                        market.setData(Uri.parse("market://details?id=" + TICKET12306_PACKAGE));
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

    @JavascriptInterface
    public String startGrab(final String trainCode, final String from, final String to,
                            final String date, final String seat) {
        if (grabRunning) {
            try {
                return new JSONObject().put("success", false).put("message", "抢票已在运行中").toString();
            } catch (Exception e) {
                return "{\"success\":false}";
            }
        }
        grabRunning = true;
        grabSuccess = false;
        grabLogs.clear();
        addLog("抢票任务已启动: " + trainCode + " " + from + "→" + to + " " + date);

        new Thread(new Runnable() {
            @Override
            public void run() {
                int attempts = 0;
                while (grabRunning && attempts < 200) {
                    attempts++;
                    addLog("第" + attempts + "次查询余票...");
                    try {
                        org.json.JSONObject result = TrainApi.queryLeftTicket(from, to, date);
                        org.json.JSONArray trains = result.optJSONArray("trains");
                        if (trains != null) {
                            for (int i = 0; i < trains.length(); i++) {
                                org.json.JSONObject t = trains.getJSONObject(i);
                                if (t.optString("code").equalsIgnoreCase(trainCode)) {
                                    String seatText = t.optString("seatText", "");
                                    if (!seatText.contains("无票") && !seatText.isEmpty()) {
                                        addLog("✅ 发现有票! " + trainCode + " " + seatText);
                                        grabSuccess = true;
                                        grabRunning = false;
                                        return;
                                    }
                                }
                            }
                        }
                        addLog("暂无票，等待重试...");
                    } catch (Exception e) {
                        addLog("查询异常: " + e.getMessage());
                    }
                    try { Thread.sleep(3000); } catch (InterruptedException e) { break; }
                }
                addLog(grabSuccess ? "抢票成功！" : "抢票任务结束");
                grabRunning = false;
            }
        }).start();

        try {
            return new JSONObject().put("success", true).put("message", "抢票已启动").toString();
        } catch (Exception e) {
            return "{\"success\":true}";
        }
    }

    @JavascriptInterface
    public void stopGrab() {
        grabRunning = false;
        addLog("用户手动停止抢票");
    }

    @JavascriptInterface
    public String getGrabStatus() {
        try {
            JSONObject obj = new JSONObject();
            obj.put("running", grabRunning);
            obj.put("success", grabSuccess);
            obj.put("logs", new org.json.JSONArray(grabLogs));
            return obj.toString();
        } catch (Exception e) {
            return "{\"running\":false,\"logs\":[]}";
        }
    }

    private void addLog(String msg) {
        String time = new SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(new Date());
        grabLogs.add("[" + time + "] " + msg);
    }
}
