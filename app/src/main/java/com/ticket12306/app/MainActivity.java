package com.ticket12306.app;

import android.annotation.SuppressLint;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.ProgressBar;

import androidx.appcompat.app.AppCompatActivity;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

public class MainActivity extends AppCompatActivity {

    private WebView webView;
    private WebView loginWebView;
    private SwipeRefreshLayout swipeRefresh;
    private ProgressBar progressBar;
    private FrameLayout loginContainer;

    private static final String TICKET12306_APP_SCHEME = "mct12306://";
    private static final String LOGIN_URL = "https://kyfw.12306.cn/otn/view/login.html";

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        swipeRefresh = findViewById(R.id.swipeRefresh);
        progressBar = findViewById(R.id.progressBar);
        webView = findViewById(R.id.webView);
        loginContainer = findViewById(R.id.loginContainer);

        initWebView();
        setupSwipeRefresh();

        webView.addJavascriptInterface(new AndroidBridge(this), "AndroidBridge");
        webView.loadUrl("file:///android_asset/index.html");
    }

    public void showLoginWebView() {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                if (loginWebView == null) {
                    loginWebView = new WebView(MainActivity.this);
                    WebSettings s = loginWebView.getSettings();
                    s.setJavaScriptEnabled(true);
                    s.setDomStorageEnabled(true);
                    s.setUseWideViewPort(true);
                    s.setLoadWithOverviewMode(true);
                    s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

                    CookieManager cm = CookieManager.getInstance();
                    cm.setAcceptCookie(true);
                    cm.setAcceptThirdPartyCookies(loginWebView, true);

                    loginWebView.setWebViewClient(new WebViewClient() {
                        @Override
                        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                            String url = request.getUrl().toString();
                            if (url.startsWith(TICKET12306_APP_SCHEME)) {
                                try {
                                    Intent intent = new Intent(Intent.ACTION_VIEW);
                                    intent.setPackage("com.MobileTicket");
                                    intent.setData(request.getUrl());
                                    startActivity(intent);
                                } catch (Exception e) { /* ignore */ }
                                return true;
                            }
                            return false;
                        }

                        @Override
                        public void onPageFinished(WebView view, String url) {
                            super.onPageFinished(view, url);
                            // 捕获 cookie
                            captureCookies();
                        }
                    });

                    loginWebView.setWebChromeClient(new WebChromeClient());
                    loginContainer.addView(loginWebView);
                }

                // 同步主 WebView 的 cookie 到登录 WebView
                CookieManager.getInstance().flush();

                loginWebView.setVisibility(View.VISIBLE);
                loginContainer.setVisibility(View.VISIBLE);
                loginWebView.loadUrl(LOGIN_URL);
            }
        });
    }

    public void hideLoginWebView() {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                if (loginWebView != null) {
                    captureCookies();
                    loginWebView.setVisibility(View.GONE);
                    loginContainer.setVisibility(View.GONE);
                }
            }
        });
    }

    private void captureCookies() {
        try {
            CookieManager cm = CookieManager.getInstance();
            String cookies = cm.getCookie("https://kyfw.12306.cn");
            if (cookies != null && !cookies.isEmpty()) {
                TrainApi.saveCookies(this, cookies);
            }
        } catch (Exception e) { /* ignore */ }
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

        // 启用 cookie 管理
        CookieManager.getInstance().setAcceptCookie(true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String url = uri.toString();

                if (url.startsWith(TICKET12306_APP_SCHEME)) {
                    try {
                        Intent intent = new Intent(Intent.ACTION_VIEW);
                        intent.setPackage("com.MobileTicket");
                        intent.setData(uri);
                        startActivity(intent);
                    } catch (Exception e) {
                        Intent web = new Intent(Intent.ACTION_VIEW);
                        web.setData(Uri.parse("https://www.12306.cn"));
                        startActivity(web);
                    }
                    return true;
                }

                if (!url.startsWith("file:///android_asset")) {
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

    @Override
    public void onBackPressed() {
        if (loginContainer.getVisibility() == View.VISIBLE && loginWebView != null && loginWebView.canGoBack()) {
            loginWebView.goBack();
        } else if (loginContainer.getVisibility() == View.VISIBLE) {
            hideLoginWebView();
        } else if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        webView.onResume();
        // 从其他 App 返回时检查 cookie
        captureCookies();
    }

    @Override
    protected void onPause() {
        super.onPause();
        webView.onPause();
        captureCookies();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        captureCookies();
        webView.destroy();
        if (loginWebView != null) loginWebView.destroy();
    }
}
