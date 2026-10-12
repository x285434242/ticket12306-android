package com.ticket12306.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.webkit.CookieManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.util.HashMap;
import java.util.Map;

public class TrainApi {

    private static final Map<String, String> STATION_CODES = new HashMap<>();
    static {
        STATION_CODES.put("北京", "BJP"); STATION_CODES.put("北京西", "BXP");
        STATION_CODES.put("北京南", "VNP"); STATION_CODES.put("北京北", "VAP");
        STATION_CODES.put("北京朝阳", "IFP"); STATION_CODES.put("上海", "SHH");
        STATION_CODES.put("上海虹桥", "AOH"); STATION_CODES.put("上海南", "SNH");
        STATION_CODES.put("广州", "GZQ"); STATION_CODES.put("广州南", "IZQ");
        STATION_CODES.put("广州东", "GGQ"); STATION_CODES.put("深圳", "SZQ");
        STATION_CODES.put("深圳北", "IOQ"); STATION_CODES.put("深圳东", "BJQ");
        STATION_CODES.put("成都", "CDW"); STATION_CODES.put("成都东", "ICW");
        STATION_CODES.put("重庆", "CQW"); STATION_CODES.put("重庆北", "CUW");
        STATION_CODES.put("重庆西", "CXW"); STATION_CODES.put("武汉", "WHN");
        STATION_CODES.put("武昌", "WCN"); STATION_CODES.put("汉口", "HKN");
        STATION_CODES.put("西安", "XAY"); STATION_CODES.put("西安北", "EAY");
        STATION_CODES.put("杭州", "HZH"); STATION_CODES.put("杭州东", "HGH");
        STATION_CODES.put("南京", "NJH"); STATION_CODES.put("南京南", "NKH");
        STATION_CODES.put("天津", "TJP"); STATION_CODES.put("天津西", "TXP");
        STATION_CODES.put("长沙", "CSQ"); STATION_CODES.put("长沙南", "CWQ");
        STATION_CODES.put("郑州", "ZZF"); STATION_CODES.put("郑州东", "ZAF");
        STATION_CODES.put("合肥", "HFH"); STATION_CODES.put("合肥南", "ENH");
        STATION_CODES.put("苏州", "SZH"); STATION_CODES.put("苏州北", "OHH");
        STATION_CODES.put("无锡", "WXH"); STATION_CODES.put("青岛", "QDK");
        STATION_CODES.put("青岛北", "QHK"); STATION_CODES.put("济南", "JNK");
        STATION_CODES.put("济南西", "JGK"); STATION_CODES.put("大连", "DLT");
        STATION_CODES.put("沈阳", "SYT"); STATION_CODES.put("沈阳北", "SBT");
        STATION_CODES.put("哈尔滨", "HBB"); STATION_CODES.put("哈尔滨西", "VAB");
        STATION_CODES.put("昆明", "KMM"); STATION_CODES.put("昆明南", "KOM");
        STATION_CODES.put("贵阳", "GIW"); STATION_CODES.put("贵阳北", "KQW");
        STATION_CODES.put("南宁", "NNZ"); STATION_CODES.put("福州", "FZS");
        STATION_CODES.put("厦门", "XMS"); STATION_CODES.put("厦门北", "XKS");
        STATION_CODES.put("南昌", "NCG"); STATION_CODES.put("南昌西", "NXG");
        STATION_CODES.put("石家庄", "SJP"); STATION_CODES.put("太原", "TYV");
        STATION_CODES.put("兰州", "LZJ"); STATION_CODES.put("兰州西", "LAJ");
        STATION_CODES.put("银川", "YIJ"); STATION_CODES.put("西宁", "XNO");
        STATION_CODES.put("呼和浩特", "HHC"); STATION_CODES.put("随州", "SZN");
        STATION_CODES.put("襄阳", "XFN"); STATION_CODES.put("宜昌", "HAN");
        STATION_CODES.put("株洲", "ZSQ"); STATION_CODES.put("衡阳", "HYQ");
        STATION_CODES.put("岳阳", "YYQ"); STATION_CODES.put("九江", "JJG");
        STATION_CODES.put("赣州", "GZG"); STATION_CODES.put("温州", "RZH");
        STATION_CODES.put("温州南", "VRH"); STATION_CODES.put("宁波", "NGH");
        STATION_CODES.put("金华", "JBH"); STATION_CODES.put("徐州", "XCH");
        STATION_CODES.put("徐州东", "UUH"); STATION_CODES.put("连云港", "UIH");
        STATION_CODES.put("南通", "NUH"); STATION_CODES.put("常州", "CZH");
        STATION_CODES.put("烟台", "YAK"); STATION_CODES.put("威海", "WHK");
        STATION_CODES.put("洛阳", "LYF"); STATION_CODES.put("开封", "KFF");
        STATION_CODES.put("信阳", "XIF"); STATION_CODES.put("南阳", "NYF");
        STATION_CODES.put("桂林", "GLZ"); STATION_CODES.put("柳州", "LZZ");
        STATION_CODES.put("三亚", "SEQ"); STATION_CODES.put("海口", "VUQ");
    }

    public static String getStationCode(String name) {
        if (name == null || name.isEmpty()) return "";
        name = name.trim();
        String code = STATION_CODES.get(name);
        if (code != null) return code;
        for (Map.Entry<String, String> e : STATION_CODES.entrySet()) {
            if (e.getKey().contains(name) || name.contains(e.getKey())) return e.getValue();
        }
        return "";
    }

    private static String getSavedCookies(Context ctx) {
        try {
            SharedPreferences sp = ctx.getSharedPreferences("login", Context.MODE_PRIVATE);
            return sp.getString("cookies", "");
        } catch (Exception e) {
            return "";
        }
    }

    public static void saveCookies(Context ctx, String cookies) {
        SharedPreferences sp = ctx.getSharedPreferences("login", Context.MODE_PRIVATE);
        sp.edit().putString("cookies", cookies).apply();
    }

    public static boolean isLoggedIn(Context ctx) {
        String c = getSavedCookies(ctx);
        return c.contains("RAIL_EXPIRATION") || c.contains("JSESSIONID") || c.contains("_jc_save_fromStation");
    }

    public static void clearCookies(Context ctx) {
        ctx.getSharedPreferences("login", Context.MODE_PRIVATE).edit().clear().apply();
    }

    private static JSONObject httpGet(Context ctx, String url) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        conn.setRequestMethod("GET");
        conn.setConnectTimeout(15000);
        conn.setReadTimeout(15000);
        conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36");
        conn.setRequestProperty("Accept", "application/json, text/javascript, */*; q=0.01");
        conn.setRequestProperty("Referer", "https://kyfw.12306.cn/otn/leftTicket/init");
        conn.setRequestProperty("X-Requested-With", "XMLHttpRequest");
        String cookies = getSavedCookies(ctx);
        if (!cookies.isEmpty()) conn.setRequestProperty("Cookie", cookies);

        int code = conn.getResponseCode();
        if (code != 200) throw new RuntimeException("HTTP " + code);

        BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), "UTF-8"));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) sb.append(line);
        reader.close();
        conn.disconnect();
        return new JSONObject(sb.toString());
    }

    private static JSONObject httpPost(Context ctx, String url, String body) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        conn.setRequestMethod("POST");
        conn.setConnectTimeout(15000);
        conn.setReadTimeout(15000);
        conn.setDoOutput(true);
        conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36");
        conn.setRequestProperty("Accept", "application/json, text/javascript, */*; q=0.01");
        conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8");
        conn.setRequestProperty("Referer", "https://kyfw.12306.cn/otn/leftTicket/init");
        conn.setRequestProperty("X-Requested-With", "XMLHttpRequest");
        String cookies = getSavedCookies(ctx);
        if (!cookies.isEmpty()) conn.setRequestProperty("Cookie", cookies);

        OutputStream os = conn.getOutputStream();
        os.write(body.getBytes("UTF-8"));
        os.flush();
        os.close();

        int code = conn.getResponseCode();
        if (code != 200) throw new RuntimeException("HTTP " + code);

        BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), "UTF-8"));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) sb.append(line);
        reader.close();
        conn.disconnect();
        return new JSONObject(sb.toString());
    }

    public static JSONObject queryLeftTicket(Context ctx, String fromName, String toName, String date) {
        try {
            String fromCode = getStationCode(fromName);
            String toCode = getStationCode(toName);
            if (fromCode.isEmpty()) return err("找不到出发地: " + fromName);
            if (toCode.isEmpty()) return err("找不到目的地: " + toName);

            String url = "https://kyfw.12306.cn/otn/leftTicket/queryG" +
                    "?leftTicketDTO.train_date=" + URLEncoder.encode(date, "UTF-8") +
                    "&leftTicketDTO.from_station=" + fromCode +
                    "&leftTicketDTO.to_station=" + toCode +
                    "&purpose_codes=ADULT";

            JSONObject resp = httpGet(ctx, url);
            JSONObject data = resp.optJSONObject("data");
            if (data == null) return err("接口返回异常");

            JSONArray rows = null;
            JSONObject result = data.optJSONObject("result");
            if (result != null) rows = result.optJSONArray("rows");
            if (rows == null) rows = data.optJSONArray("result");
            if (rows == null) return ok(new JSONArray());

            JSONObject stationMap = data.optJSONObject("map");
            JSONArray trains = new JSONArray();
            for (int i = 0; i < Math.min(rows.length(), 30); i++) {
                String row = rows.getString(i);
                String[] f = row.split("\\|");
                if (f.length < 33) continue;
                String code = f[3];
                if (code.isEmpty()) continue;

                String fromName2 = stationMap != null ? stationMap.optString(f[6], f[6]) : f[6];
                String toName2 = stationMap != null ? stationMap.optString(f[7], f[7]) : f[7];

                StringBuilder seat = new StringBuilder();
                if (!f[32].isEmpty() && !f[32].equals("无")) seat.append("二等").append(f[32]).append(" ");
                if (!f[31].isEmpty() && !f[31].equals("无")) seat.append("一等").append(f[31]).append(" ");
                if (!f[30].isEmpty() && !f[30].equals("无")) seat.append("商务").append(f[30]).append(" ");
                if (!f[28].isEmpty() && !f[28].equals("无")) seat.append("硬卧").append(f[28]).append(" ");
                if (!f[24].isEmpty() && !f[24].equals("无")) seat.append("硬座").append(f[24]).append(" ");
                if (!f[33].isEmpty() && !f[33].equals("无")) seat.append("软卧").append(f[33]).append(" ");
                if (seat.length() == 0) seat.append("无票");

                JSONObject t = new JSONObject();
                t.put("code", code);
                t.put("from", fromName2);
                t.put("to", toName2);
                t.put("depart", f[8]);
                t.put("arrive", f[9]);
                t.put("seatText", seat.toString().trim());
                trains.put(t);
            }
            return ok(trains);
        } catch (Exception e) {
            return err(e.getMessage());
        }
    }

    public static JSONObject getPassengers(Context ctx) {
        try {
            JSONObject resp = httpPost(ctx,
                "https://kyfw.12306.cn/otn/confirm passengers/getPassengerDTOs",
                "REPEAT_SUBMIT_TOKEN=");
            JSONObject data = resp.optJSONObject("data");
            if (data == null) return err("获取乘车人失败，请先登录");
            JSONArray normals = data.optJSONArray("normal_passengers");
            if (normals == null) return err("无乘车人数据");

            JSONArray list = new JSONArray();
            for (int i = 0; i < normals.length(); i++) {
                JSONObject p = normals.getJSONObject(i);
                JSONObject item = new JSONObject();
                item.put("name", p.optString("passenger_name", ""));
                item.put("idType", p.optString("passenger_id_type_code", ""));
                item.put("idNo", p.optString("passenger_id_no", ""));
                item.put("phone", p.optString("mobile_no", ""));
                list.put(item);
            }
            JSONObject result = new JSONObject();
            result.put("success", true);
            result.put("passengers", list);
            return result;
        } catch (Exception e) {
            return err(e.getMessage());
        }
    }

    public static JSONObject submitOrder(Context ctx, String trainCode, String date,
                                          String seatType, String fromName, String toName,
                                          JSONArray passengers) {
        try {
            String fromCode = getStationCode(fromName);
            String toCode = getStationCode(toName);

            // 1. 获取提交订单所需的 token
            JSONObject initResp = httpGet(ctx,
                "https://kyfw.12306.cn/otn/leftTicket/init?linktypeid=dc");
            // 从 init 页面提取全局 token
            String globalRepeatSubmitToken = "";
            // 尝试从 getPassengerDTOs 获取
            JSONObject passResp = httpPost(ctx,
                "https://kyfw.12306.cn/otn/confirm passengers/getPassengerDTOs",
                "REPEAT_SUBMIT_TOKEN=");
            JSONObject pData = passResp.optJSONObject("data");
            if (pData != null) {
                globalRepeatSubmitToken = pData.optString("token", "");
            }

            // 2. 提交订单
            StringBuilder sb = new StringBuilder();
            sb.append("repeatSubmitToken=").append(URLEncoder.encode(globalRepeatSubmitToken, "UTF-8"));
            sb.append("&train_date=").append(URLEncoder.encode(date, "UTF-8"));
            sb.append("&back_train_date=").append(URLEncoder.encode(date, "UTF-8"));
            sb.append("&tour_flag=0");
            sb.append("&purpose_codes=ADULT");
            sb.append("&query_from_station_name=").append(URLEncoder.encode(fromName, "UTF-8"));
            sb.append("&query_to_station_name=").append(URLEncoder.encode(toName, "UTF-8"));
            sb.append("&undefined=");

            // 设置乘客
            StringBuilder passengerTicketStr = new StringBuilder();
            StringBuilder oldPassengerStr = new StringBuilder();
            for (int i = 0; i < passengers.length(); i++) {
                JSONObject p = passengers.getJSONObject(i);
                String pid = p.optString("idNo", "");
                String pname = p.optString("name", "");
                if (i > 0) { passengerTicketStr.append("_"); oldPassengerStr.append("_"); }
                passengerTicketStr.append(seatType).append(",0,1,").append(pid).append(",").append(pname).append(",N,1,");
                oldPassengerStr.append(pname).append(",1,").append(pid).append(",1_");
            }

            sb.append("&passengerTicketStr=").append(URLEncoder.encode(passengerTicketStr.toString(), "UTF-8"));
            sb.append("&oldPassengerStr=").append(URLEncoder.encode(oldPassengerStr.toString(), "UTF-8"));

            JSONObject orderResp = httpPost(ctx,
                "https://kyfw.12306.cn/otn/leftTicket/submitOrderRequest",
                sb.toString());

            JSONObject result = new JSONObject();
            result.put("success", orderResp.optBoolean("status", false));
            result.put("message", orderResp.optJSONObject("messages") != null ?
                orderResp.optJSONObject("messages").toString() : "订单提交结果未知");
            return result;
        } catch (Exception e) {
            return err(e.getMessage());
        }
    }

    private static JSONObject ok(JSONArray trains) {
        try {
            JSONObject o = new JSONObject();
            o.put("success", true);
            o.put("trains", trains);
            return o;
        } catch (Exception e) { return new JSONObject(); }
    }

    private static JSONObject err(String msg) {
        try {
            JSONObject o = new JSONObject();
            o.put("success", false);
            o.put("message", msg != null ? msg : "unknown");
            return o;
        } catch (Exception e) { return new JSONObject(); }
    }
}
