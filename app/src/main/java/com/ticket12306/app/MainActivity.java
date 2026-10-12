package com.ticket12306.app;

import android.annotation.SuppressLint;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ProgressBar;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends AppCompatActivity {

    private static final String TAG = "MainActivity";
    private static final int PORT = 8765;
    private static final String LOCAL_URL = "http://127.0.0.1:" + PORT;

    private WebView webView;
    private SwipeRefreshLayout swipeRefresh;
    private ProgressBar progressBar;
    private boolean pageLoaded = false;

    private static final String TICKET12306_PACKAGE = "com.MobileTicket";
    private static final String TICKET12306_APP_SCHEME = "mct12306://";

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        swipeRefresh = findViewById(R.id.swipeRefresh);
        progressBar = findViewById(R.id.progressBar);
        webView = findViewById(R.id.webView);

        initWebView();
        setupSwipeRefresh();

        startBackendService();
        loadWhenReady();
    }

    private void loadWhenReady() {
        progressBar.setVisibility(View.VISIBLE);
        new Thread(() -> {
            for (int i = 0; i < 120; i++) {
                try {
                    URL url = new URL(LOCAL_URL);
                    HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                    conn.setConnectTimeout(800);
                    conn.setReadTimeout(800);
                    int code = conn.getResponseCode();
                    conn.disconnect();
                    if (code == 200) {
                        runOnUiThread(() -> {
                            pageLoaded = false;
                            webView.loadUrl(LOCAL_URL);
                        });
                        return;
                    }
                } catch (Exception ignored) {}
                try { Thread.sleep(500); } catch (InterruptedException e) { return; }
            }
            runOnUiThread(() -> {
                progressBar.setVisibility(View.GONE);
                Toast.makeText(this, "本地服务启动超时，请下拉刷新重试", Toast.LENGTH_LONG).show();
            });
        }).start();
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void initWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String url = uri.toString();

                // 拦截 12306 App 深度链接
                if (url.startsWith(TICKET12306_APP_SCHEME)) {
                    openTicket12306App(url);
                    return true;
                }

                // 非本地 URL 用浏览器打开
                if (!url.startsWith("http://127.0.0.1") && !url.startsWith("http://localhost")) {
                    Intent intent = new Intent(Intent.ACTION_VIEW, uri);
                    startActivity(intent);
                    return true;
                }

                return false;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                pageLoaded = true;
                swipeRefresh.setRefreshing(false);
                progressBar.setVisibility(View.GONE);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request.isForMainFrame()) {
                    pageLoaded = false;
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
                progressBar.setVisibility(newProgress < 100 ? View.VISIBLE : View.GONE);
            }
        });
    }

    private void setupSwipeRefresh() {
        swipeRefresh.setColorSchemeResources(
            android.R.color.holo_blue_bright,
            android.R.color.holo_green_light,
            android.R.color.holo_orange_light
        );
        swipeRefresh.setOnRefreshListener(() -> {
            if (pageLoaded) {
                webView.reload();
            } else {
                loadWhenReady();
            }
        });
    }

    private void startBackendService() {
        Intent serviceIntent = new Intent(this, BackendService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent);
        } else {
            startService(serviceIntent);
        }
        Toast.makeText(this, "启动本地服务...", Toast.LENGTH_SHORT).show();
    }

    private void openTicket12306App(String url) {
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setPackage(TICKET12306_PACKAGE);
            intent.setData(Uri.parse(url));
            startActivity(intent);
            Toast.makeText(this, "已跳转12306 App", Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            // App未安装，尝试跳转应用商店
            try {
                Intent marketIntent = new Intent(Intent.ACTION_VIEW);
                marketIntent.setData(Uri.parse("market://details?id=" + TICKET12306_PACKAGE));
                startActivity(marketIntent);
            } catch (Exception e2) {
                // 打开网页版
                Intent webIntent = new Intent(Intent.ACTION_VIEW);
                webIntent.setData(Uri.parse("https://www.12306.cn"));
                startActivity(webIntent);
            }
        }
    }

    public boolean isTicket12306AppInstalled() {
        try {
            getPackageManager().getPackageInfo(TICKET12306_PACKAGE, 0);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        webView.onResume();
    }

    @Override
    protected void onPause() {
        super.onPause();
        webView.onPause();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        webView.destroy();
    }
}
