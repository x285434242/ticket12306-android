package com.ticket12306.app;

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
        STATION_CODES.put("北京", "BJP");
        STATION_CODES.put("北京西", "BXP");
        STATION_CODES.put("北京南", "VNP");
        STATION_CODES.put("北京北", "VAP");
        STATION_CODES.put("北京朝阳", "IFP");
        STATION_CODES.put("上海", "SHH");
        STATION_CODES.put("上海虹桥", "AOH");
        STATION_CODES.put("上海南", "SNH");
        STATION_CODES.put("广州", "GZQ");
        STATION_CODES.put("广州南", "IZQ");
        STATION_CODES.put("广州东", "GGQ");
        STATION_CODES.put("深圳", "SZQ");
        STATION_CODES.put("深圳北", "IOQ");
        STATION_CODES.put("深圳东", "BJQ");
        STATION_CODES.put("成都", "CDW");
        STATION_CODES.put("成都东", "ICW");
        STATION_CODES.put("成都南", "CNW");
        STATION_CODES.put("重庆", "CQW");
        STATION_CODES.put("重庆北", "CUW");
        STATION_CODES.put("重庆西", "CXW");
        STATION_CODES.put("武汉", "WHN");
        STATION_CODES.put("武昌", "WCN");
        STATION_CODES.put("汉口", "HKN");
        STATION_CODES.put("西安", "XAY");
        STATION_CODES.put("西安北", "EAY");
        STATION_CODES.put("杭州", "HZH");
        STATION_CODES.put("杭州东", "HGH");
        STATION_CODES.put("南京", "NJH");
        STATION_CODES.put("南京南", "NKH");
        STATION_CODES.put("天津", "TJP");
        STATION_CODES.put("天津西", "TXP");
        STATION_CODES.put("长沙", "CSQ");
        STATION_CODES.put("长沙南", "CWQ");
        STATION_CODES.put("郑州", "ZZF");
        STATION_CODES.put("郑州东", "ZAF");
        STATION_CODES.put("合肥", "HFH");
        STATION_CODES.put("合肥南", "ENH");
        STATION_CODES.put("苏州", "SZH");
        STATION_CODES.put("苏州北", "OHH");
        STATION_CODES.put("无锡", "WXH");
        STATION_CODES.put("青岛", "QDK");
        STATION_CODES.put("青岛北", "QHK");
        STATION_CODES.put("济南", "JNK");
        STATION_CODES.put("济南西", "JGK");
        STATION_CODES.put("大连", "DLT");
        STATION_CODES.put("沈阳", "SYT");
        STATION_CODES.put("沈阳北", "SBT");
        STATION_CODES.put("哈尔滨", "HBB");
        STATION_CODES.put("哈尔滨西", "VAB");
        STATION_CODES.put("昆明", "KMM");
        STATION_CODES.put("昆明南", "KOM");
        STATION_CODES.put("贵阳", "GIW");
        STATION_CODES.put("贵阳北", "KQW");
        STATION_CODES.put("南宁", "NNZ");
        STATION_CODES.put("福州", "FZS");
        STATION_CODES.put("福州南", "FYS");
        STATION_CODES.put("厦门", "XMS");
        STATION_CODES.put("厦门北", "XKS");
        STATION_CODES.put("南昌", "NCG");
        STATION_CODES.put("南昌西", "NXG");
        STATION_CODES.put("石家庄", "SJP");
        STATION_CODES.put("太原", "TYV");
        STATION_CODES.put("太原南", "TNV");
        STATION_CODES.put("兰州", "LZJ");
        STATION_CODES.put("兰州西", "LAJ");
        STATION_CODES.put("乌鲁木齐", "WAR");
        STATION_CODES.put("银川", "YIJ");
        STATION_CODES.put("西宁", "XNO");
        STATION_CODES.put("呼和浩特", "HHC");
        STATION_CODES.put("随州", "SZN");
        STATION_CODES.put("襄阳", "XFN");
        STATION_CODES.put("宜昌", "HAN");
        STATION_CODES.put("株洲", "ZSQ");
        STATION_CODES.put("衡阳", "HYQ");
        STATION_CODES.put("岳阳", "YYQ");
        STATION_CODES.put("九江", "JJG");
        STATION_CODES.put("赣州", "GZG");
        STATION_CODES.put("温州", "RZH");
        STATION_CODES.put("温州南", "VRH");
        STATION_CODES.put("宁波", "NGH");
        STATION_CODES.put("金华", "JBH");
        STATION_CODES.put("徐州", "XCH");
        STATION_CODES.put("徐州东", "UUH");
        STATION_CODES.put("连云港", "UIH");
        STATION_CODES.put("南通", "NUH");
        STATION_CODES.put("常州", "CZH");
        STATION_CODES.put("烟台", "YAK");
        STATION_CODES.put("威海", "WHK");
        STATION_CODES.put("洛阳", "LYF");
        STATION_CODES.put("开封", "KFF");
        STATION_CODES.put("信阳", "XIF");
        STATION_CODES.put("南阳", "NYF");
        STATION_CODES.put("桂林", "GLZ");
        STATION_CODES.put("柳州", "LZZ");
        STATION_CODES.put("三亚", "SEQ");
        STATION_CODES.put("海口", "VUQ");
    }

    public static String getStationCode(String name) {
        if (name == null || name.isEmpty()) return "";
        String code = STATION_CODES.get(name.trim());
        if (code != null) return code;
        for (Map.Entry<String, String> e : STATION_CODES.entrySet()) {
            if (e.getKey().contains(name.trim()) || name.trim().contains(e.getKey())) {
                return e.getValue();
            }
        }
        return "";
    }

    public static JSONObject queryLeftTicket(String fromName, String toName, String date) {
        try {
            String fromCode = getStationCode(fromName);
            String toCode = getStationCode(toName);
            if (fromCode.isEmpty()) {
                return new JSONObject().put("success", false).put("message", "找不到出发地: " + fromName);
            }
            if (toCode.isEmpty()) {
                return new JSONObject().put("success", false).put("message", "找不到目的地: " + toName);
            }

            String url = "https://kyfw.12306.cn/otn/leftTicket/queryG" +
                    "?leftTicketDTO.train_date=" + URLEncoder.encode(date, "UTF-8") +
                    "&leftTicketDTO.from_station=" + fromCode +
                    "&leftTicketDTO.to_station=" + toCode +
                    "&purpose_codes=ADULT";

            HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(10000);
            conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36");
            conn.setRequestProperty("Accept", "application/json");
            conn.setRequestProperty("Referer", "https://kyfw.12306.cn/otn/leftTicket/init");
            conn.setRequestProperty("Cookie", "JSESSIONID=; _jc_save_fromStation=" +
                    URLEncoder.encode(fromName, "UTF-8") + "%2C" + fromCode +
                    "; _jc_save_toStation=" + URLEncoder.encode(toName, "UTF-8") + "%2C" + toCode +
                    "; _jc_save_fromDate=" + date);

            int code = conn.getResponseCode();
            if (code != 200) {
                return new JSONObject().put("success", false).put("message", "HTTP " + code);
            }

            BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), "UTF-8"));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) sb.append(line);
            reader.close();
            conn.disconnect();

            JSONObject resp = new JSONObject(sb.toString());
            JSONObject data = resp.optJSONObject("data");
            if (data == null) {
                return new JSONObject().put("success", false).put("message", "接口返回异常");
            }

            JSONObject result = data.optJSONObject("result");
            JSONArray rows = null;
            if (result != null) {
                rows = result.optJSONArray("rows");
            }
            if (rows == null) {
                rows = data.optJSONArray("result");
            }
            if (rows == null) {
                return new JSONObject().put("success", true).put("trains", new JSONArray());
            }

            JSONObject stationMap = data.optJSONObject("map");

            JSONArray trains = new JSONArray();
            for (int i = 0; i < Math.min(rows.length(), 30); i++) {
                String row = rows.getString(i);
                String[] fields = row.split("\\|");
                if (fields.length < 30) continue;

                String trainCode = fields[3];
                if (trainCode.isEmpty()) continue;

                String fromStationName = stationMap != null ?
                        stationMap.optString(fields[6], fields[6]) : fields[6];
                String toStationName = stationMap != null ?
                        stationMap.optString(fields[7], fields[7]) : fields[7];

                StringBuilder seatText = new StringBuilder();
                if (!fields[30].isEmpty() && !fields[30].equals("无")) seatText.append("商务 ").append(fields[30]).append(" ");
                if (!fields[31].isEmpty() && !fields[31].equals("无")) seatText.append("一等 ").append(fields[31]).append(" ");
                if (!fields[32].isEmpty() && !fields[32].equals("无")) seatText.append("二等 ").append(fields[32]).append(" ");
                if (!fields[28].isEmpty() && !fields[28].equals("无")) seatText.append("硬卧 ").append(fields[28]).append(" ");
                if (!fields[24].isEmpty() && !fields[24].equals("无")) seatText.append("硬座 ").append(fields[24]).append(" ");
                if (!fields[33].isEmpty() && !fields[33].equals("无")) seatText.append("软卧 ").append(fields[33]).append(" ");
                if (seatText.length() == 0) seatText.append("无票");

                JSONObject train = new JSONObject();
                train.put("code", trainCode);
                train.put("from", fromStationName);
                train.put("to", toStationName);
                train.put("depart", fields[8]);
                train.put("arrive", fields[9]);
                train.put("seatText", seatText.toString().trim());
                trains.put(train);
            }

            return new JSONObject().put("success", true).put("trains", trains);

        } catch (Exception e) {
            return new JSONObject().put("success", false).put("message", e.getMessage());
        }
    }
}
