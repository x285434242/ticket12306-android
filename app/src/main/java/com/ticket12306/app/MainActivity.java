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
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ProgressBar;
import android.widget.Toast;

import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

public class MainActivity extends AppCompatActivity {

    private static final String TAG = "MainActivity";
    private static final int PORT = 8765;
    private static final String LOCAL_URL = "http://127.0.0.1:" + PORT;

    private WebView webView;
    private SwipeRefreshLayout swipeRefresh;
    private ProgressBar progressBar;
    private BackendService backendService;
    private boolean isServiceRunning = false;

    // 12306 App 相关
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

        // 启动本地后端服务
        startBackendService();

        // 延迟加载页面，等待服务启动
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            webView.loadUrl(LOCAL_URL);
        }, 1500);
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
                swipeRefresh.setRefreshing(false);
                progressBar.setVisibility(View.GONE);
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
        swipeRefresh.setOnRefreshListener(() -> webView.reload());
    }

    private void startBackendService() {
        Intent serviceIntent = new Intent(this, BackendService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent);
        } else {
            startService(serviceIntent);
        }
        isServiceRunning = true;
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
        if (isServiceRunning) {
            stopService(new Intent(this, BackendService.class));
        }
        webView.destroy();
    }
}
