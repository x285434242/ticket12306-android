package com.ticket12306.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

public class BackendService extends Service {

    private static final String TAG = "BackendService";
    private static final String CHANNEL_ID = "backend_service";
    private static final int NOTIFICATION_ID = 1;
    private static final int PORT = 8765;

    private PyObject pythonServer;

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        try {
            if (Build.VERSION.SDK_INT >= 34) {
                startForeground(NOTIFICATION_ID, buildNotification("服务启动中..."),
                        android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
            } else {
                startForeground(NOTIFICATION_ID, buildNotification("服务启动中..."));
            }
        } catch (Exception e) {
            Log.e(TAG, "startForeground failed", e);
            try {
                startForeground(NOTIFICATION_ID, buildNotification("服务启动中..."));
            } catch (Exception e2) {
                Log.e(TAG, "startForeground fallback failed", e2);
            }
        }

        new Thread(() -> {
            try {
                if (!Python.isStarted()) {
                    Python.start(new AndroidPlatform(this));
                }

                Python py = Python.getInstance();
                PyObject mainModule = py.getModule("main");

                updateNotification("12306抢票服务运行中");

                // 启动服务器（阻塞调用，永久阻塞在此线程）
                mainModule.callAttr("start_server", PORT);

            } catch (Exception e) {
                Log.e(TAG, "Failed to start Python server", e);
                updateNotification("服务启动失败: " + e.getMessage());
                stopSelf();
            }
        }).start();

        return START_STICKY;
    }

    private Notification buildNotification(String text) {
        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(this, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(this);
        }

        return builder
                .setContentTitle("12306抢票助手")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_menu_agenda)
                .setOngoing(true)
                .build();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "抢票服务",
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("12306抢票后台服务");
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    private void updateNotification(String text) {
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) {
            manager.notify(NOTIFICATION_ID, buildNotification(text));
        }
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        Log.d(TAG, "Service destroyed");
    }
}
