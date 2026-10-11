# 12306抢票助手 Android 版

手机本地运行，无需外部服务器！APK 内置 Python 后端 + WebView 前端。

## 架构

```
┌─────────────────────────────────┐
│           Android APK           │
├─────────────────────────────────┤
│  WebView (前端界面)             │
│         ↕ localhost:8765        │
│  Chaquopy (内嵌Python)          │
│  ├── main.py (HTTP服务)         │
│  └── 12306-train-assistant/     │
│      ├── client.py (12306客户端)│
│      └── server.py (业务逻辑)   │
└─────────────────────────────────┘
```

## 功能

- ✅ 手机本地运行，无需服务器
- ✅ 账号密码登录 / 二维码登录
- ✅ 跳转 12306 App 授权登录
- ✅ 余票查询
- ✅ 自动抢票
- ✅ 后台服务持续运行

## 编译方法

### GitHub Actions 自动编译（推荐）

1. 推送代码到 GitHub：
```bash
cd app
git init
git add .
git commit -m "Android APK"
git remote add origin https://github.com/你的用户名/你的仓库名.git
git push -u origin main
```

2. 等待 Actions 编译完成（约3-5分钟）

3. 在 **Actions** → 最新任务 → **Artifacts** 下载 APK

### 本地编译

需要：JDK 17+、Android SDK

```bash
cd app
./gradlew assembleDebug
# 输出: app/build/outputs/apk/debug/app-debug.apk
```

## 安装使用

1. 手机允许安装未知来源应用
2. 安装 APK
3. 打开应用，允许通知权限（后台服务需要）
4. 登录 12306 账号
5. 查询车票 → 开始抢票

## 登录方式

| 方式 | 说明 |
|------|------|
| 账号密码 | 直接输入12306账号密码 |
| 二维码 | 使用12306 App扫码 |
| App授权 | 跳转已安装的12306 App授权 |

## 注意事项

- APK 内置完整 Python 环境，首次启动约 30MB
- 抢票时保持应用在后台运行
- 建议在 WiFi 环境下使用
