// -----------------------------------------------------------------------------
// NOTE (Arduino build quirk):
// The Arduino preprocessor auto-generates function prototypes near the top of
// the sketch. If a generated prototype uses a user-defined type declared later
// (e.g. BaseUrl, Reading), compilation fails.
// Forward-declare these types here so the generated prototypes compile.
// -----------------------------------------------------------------------------
struct BaseUrl;
struct Reading;

#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <WiFiManager.h>
#include <Wire.h>

#include <Adafruit_INA219.h>
#include <Adafruit_SHT31.h>
#include <BH1750.h>

#include <TinyGPSPlus.h>
#include <U8g2lib.h>

#include "icons.h"
#include "qrcode.h"

#include "esp_idf_version.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "mbedtls/md.h"
#include <esp_wifi.h>
#include <math.h>
#include <strings.h>

// ===================== BUILD / DEFAULTS =====================
static const char *FIRMWARE_VERSION = "ws-esp32-1.1.1";

static const int PIN_I2C_SDA = 21;
static const int PIN_I2C_SCL = 22;

static const int PIN_GPS_RX = 16;
static const int PIN_GPS_TX = 17;
static const uint32_t GPS_BAUD = 9600;

static const int PIN_MQ135_ADC = 36;
static const int PIN_FORCE_PORTAL = 0;
static const int PIN_WIFI_LED = 2;

// Forward declaration for QR portal rendering (u8g2 object is defined later)
extern U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2;

// ===================== WIFI PORTAL (QR ON OLED) =====================
// NOTE: WiFiManager portal password must be >= 8 chars for WPA2.
static const char *PORTAL_PASS = "wsportal";

static String g_portalSsid;
static String g_portalPass;
static IPAddress g_portalIP;
static String g_wifiQrText;

static String escapeWiFiField(const String &in) {
  String out;
  out.reserve(in.length() + 8);
  for (size_t i = 0; i < in.length(); i++) {
    char c = in[i];
    if (c == '\\' || c == ';' || c == ',' || c == ':' || c == '"')
      out += '\\';
    out += c;
  }
  return out;
}

static String clipText(const String &s, size_t maxLen) {
  if (s.length() <= maxLen)
    return s;
  if (maxLen <= 3)
    return s.substring(0, maxLen);
  return s.substring(0, maxLen - 3) + "...";
}

static void portalQRDisplay(esp_qrcode_handle_t qrcode) {
  u8g2.clearBuffer();

  const int size = esp_qrcode_get_size(qrcode);
  const int quiet = 1;
  const int margin = 1;
  const int avail = 64 - 2 * margin;

  int scale = avail / (size + 2 * quiet);
  if (scale < 1)
    scale = 1;

  int qrTotal = (size + 2 * quiet) * scale;
  int qrX = 0;
  int qrY = (64 - qrTotal) / 2;
  if (qrY < 0)
    qrY = 0;

  // White background
  u8g2.setDrawColor(1);
  u8g2.drawBox(qrX, qrY, qrTotal, qrTotal);

  // Black modules
  u8g2.setDrawColor(0);
  for (int y = 0; y < size; y++) {
    for (int x = 0; x < size; x++) {
      if (esp_qrcode_get_module(qrcode, x, y)) {
        int px = qrX + (x + quiet) * scale;
        int py = qrY + (y + quiet) * scale;
        u8g2.drawBox(px, py, scale, scale);
      }
    }
  }
  u8g2.setDrawColor(1);

  const int tx = qrX + qrTotal + 4;

  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.setCursor(tx, 12);
  u8g2.print("WiFi AP:");
  u8g2.setFont(u8g2_font_5x7_tf);
  u8g2.setCursor(tx, 22);
  u8g2.print(clipText(g_portalSsid, 16));

  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.setCursor(tx, 38);
  u8g2.print("Pass:");
  u8g2.setFont(u8g2_font_5x7_tf);
  u8g2.setCursor(tx, 48);
  if (g_portalPass.length()) {
    u8g2.print(clipText(g_portalPass, 16));
  } else {
    u8g2.print("(open)");
  }

  u8g2.setFont(u8g2_font_5x7_tf);
  u8g2.setCursor(tx, 62);
  u8g2.print(g_portalIP.toString());

  u8g2.sendBuffer();
}

static void showPortalWithQR(const String &apSsid, const String &apPass,
                             const IPAddress &ip) {
  g_portalSsid = apSsid;
  g_portalPass = apPass;
  g_portalIP = ip;

  const String ssidEsc = escapeWiFiField(apSsid);
  const String passEsc = escapeWiFiField(apPass);

  // Target: QR harus selalu bisa di-generate dan tetap mungkin di-scan di OLED
  // 128x64. Karena resolusi kecil, kita prefer versi QR rendah (<=3) supaya
  // modul masih cukup besar. Jika payload WiFi terlalu panjang, fallback ke QR
  // URL portal (tetap berguna: scan untuk buka portal).
  const bool apOpen = (apPass.length() < 8); // WiFiManager treat <8 as open

  String wifiQr;
  if (apOpen) {
    // WiFi QR standard open AP: WIFI:T:nopass;S:<ssid>;;
    wifiQr = "WIFI:T:nopass;S:" + ssidEsc + ";;";
  } else {
    // WiFi QR standard WPA: WIFI:T:WPA;S:<ssid>;P:<pass>;;
    wifiQr = "WIFI:T:WPA;S:" + ssidEsc + ";P:" + passEsc + ";;";
  }

  esp_qrcode_config_t cfg = ESP_QRCODE_CONFIG_DEFAULT();
  cfg.display_func = portalQRDisplay;
  cfg.max_qrcode_version = 3; // keep scan-friendly on 128x64
  cfg.qrcode_ecc_level = ESP_QRCODE_ECC_LOW;

  esp_err_t retWifi = esp_qrcode_generate(&cfg, wifiQr.c_str());
  if (retWifi == ESP_OK) {
    g_wifiQrText = wifiQr;
    Serial.printf("[QR] wifi ok (open=%d) len=%u\n", apOpen ? 1 : 0,
                  (unsigned)wifiQr.length());
    return;
  }

  // Fallback: QR URL portal (short, always fits, still useful)
  const String urlQr = "http://" + ip.toString();
  esp_err_t retUrl = esp_qrcode_generate(&cfg, urlQr.c_str());
  if (retUrl == ESP_OK) {
    g_wifiQrText = urlQr;
    Serial.printf("[QR] wifi failed ret=%d len=%u -> url ok len=%u\n",
                  (int)retWifi, (unsigned)wifiQr.length(),
                  (unsigned)urlQr.length());
    return;
  }

  // Ultimate fallback: text-only
  Serial.printf("[QR] generate failed wifi_ret=%d url_ret=%d\n", (int)retWifi,
                (int)retUrl);
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.drawStr(0, 12, "QR generate FAILED");
  u8g2.setFont(u8g2_font_5x7_tf);
  u8g2.setCursor(0, 28);
  u8g2.print("AP: ");
  u8g2.print(apSsid);
  u8g2.setCursor(0, 40);
  u8g2.print("PASS: ");
  u8g2.print(apPass.length() ? apPass : "(open)");
  u8g2.setCursor(0, 52);
  u8g2.print("IP: ");
  u8g2.print(ip.toString());
  u8g2.sendBuffer();
}

static void onAPMode(WiFiManager *myWM) {
  // Called when WiFiManager enters AP mode.
  const String apSsid = myWM->getConfigPortalSSID();
  const IPAddress ip = WiFi.softAPIP();
  showPortalWithQR(apSsid, String(PORTAL_PASS), ip);
}

static uint32_t g_sensorIntervalSec = 3; // POST interval (seconds)
static uint32_t g_commandPollIntervalSec =
    10; // command poll interval (seconds)

// Local refresh intervals (do not affect server interval unless you change
// g_sensorIntervalSec)
static uint32_t g_sensorReadPeriodMs = 400; // read sensors for OLED/serial (ms)
static uint32_t g_oledIntervalMs = 100;     // OLED refresh (ms)

// OLED paging
static bool g_oledEnabled = true;
static bool g_oledAutoPage = true;
static uint8_t g_oledPage = 0;
static uint32_t g_oledPageIntervalMs = 5000;
static uint32_t g_lastOledPageSwitchMs = 0;
static const uint8_t OLED_PAGE_COUNT = 5;

// OLED hardware settings
static uint8_t g_oledFlip = 0;
static uint8_t g_oledContrast = 255;

// OLED test pattern (transient; not persisted)
static uint8_t g_oledTestMode =
    0; // 0=off,1=black,2=white,3=checker,4=grid,5=vstripes,6=hstripes,7=bars

// WiFi
static bool g_wifiEnabled = true; // allow WiFi connect/maintain
static char g_wifiSsid[33] = {0}; // optional manual SSID (if set)
static char g_wifiPass[65] = {0}; // optional manual PASS (if set)

static bool g_tlsInsecure = true;

// Realtime serial
static bool g_rtEnabled = false;
static uint32_t g_lastRtMs = 0;

// Sensor read bookkeeping
static uint32_t g_lastSensorReadMs = 0;

// Last POST status (for OLED / diagnostics)
static int g_lastPostCode = 0;
static bool g_lastPostOk = false;
static uint32_t g_lastPostMs = 0;
// ===================== PERSISTED SETTINGS =====================
Preferences prefs;
static const char *PREF_NS = "ws";

static const char *KEY_SERVER_URL = "server_url";
static const char *KEY_DEVICE_ID = "device_id";
static const char *KEY_SECRET = "secret";
static const char *KEY_TLS_INSEC = "tls_insec";

static const char *KEY_OLED_EN = "oled_en";
static const char *KEY_OLED_FLIP = "oled_flip";
static const char *KEY_OLED_CONTR = "oled_contr";
static const char *KEY_OLED_AUTO = "oled_auto";
static const char *KEY_OLED_PAGE = "oled_page";
static const char *KEY_OLED_REF_MS = "oled_ref";
static const char *KEY_OLED_PG_MS = "oled_pg";

static const char *KEY_WIFI_EN = "wifi_en";
static const char *KEY_WIFI_SSID = "wifi_ssid";
static const char *KEY_WIFI_PASS = "wifi_pass";

static const char *KEY_SENS_MS = "sens_ms";
static const char *KEY_POST_SEC = "post_sec";
static const char *KEY_CMD_SEC = "cmd_sec";
static char g_serverUrl[160] = {0};
static char g_deviceId[64] = "esp32-1";
static char g_sharedSecret[96] = {0};

// ===================== PARSED BASE URL =====================
struct BaseUrl {
  bool https = false;
  char host[128] = {0};
  uint16_t port = 80;
  char basePath[96] = {0};
  bool valid = false;
};
static BaseUrl g_base;

// ===================== SENSORS =====================
Adafruit_SHT31 sht31 = Adafruit_SHT31();
BH1750 bh1750;
Adafruit_INA219 ina219;

static bool g_hasSHT31 = false;
static bool g_hasBH1750 = false;
static bool g_hasINA219 = false;

TinyGPSPlus gps;
HardwareSerial GPS_Serial(2);

U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

// Calibration offsets
static float g_calTemp = 0.0f;
static float g_calHum = 0.0f;
static int g_calAir = 0;
static float g_calLux = 0.0f;
static float g_calVolt = 0.0f;

// ===================== SENSOR ENABLE DEFAULTS =====================
static bool g_selGps = true;
static bool g_selInaExtras = true;

// ===================== STATE =====================
static uint32_t g_bootMs = 0;
static uint32_t g_lastSensorMs = 0;
static uint32_t g_lastCmdMs = 0;
static uint32_t g_lastOledMs = 0;

static uint32_t g_lastWiFiReconnectAttemptMs = 0;
static const uint32_t WIFI_RECONNECT_COOLDOWN_MS = 5000;

static bool g_wdtArmed = false;

static bool g_forceLegacyConfig = false;
static uint32_t g_forceLegacyUntilMs = 0;
static uint32_t g_lastCfgHash = 0;

// ===================== JSON DOCS + BUFFERS =====================
static StaticJsonDocument<1152> g_docCmd;
static StaticJsonDocument<1792> g_docLegacy;
static StaticJsonDocument<1024> g_docSend;

static char g_payloadBuf[1000];
static char g_respBuf[2200];

// ===================== OFFLINE QUEUE =====================
static const size_t OFFLINE_QUEUE_MAX = 25;
static const size_t OFFLINE_PAYLOAD_MAX = 1000;

static char g_offlineBuf[OFFLINE_QUEUE_MAX][OFFLINE_PAYLOAD_MAX];
static uint16_t g_offlineLen[OFFLINE_QUEUE_MAX];
static uint8_t g_offlineHead = 0;
static uint8_t g_offlineTail = 0;
static uint8_t g_offlineCount = 0;

// ===================== READING STRUCT =====================
struct Reading {
  float temperature = NAN;
  float humidity = NAN;
  int air_quality = 0;
  int air_quality_raw = 0;
  float light_lux = NAN;

  float bus_voltage = NAN;     // V
  float current_mA = NAN;      // mA
  float power_mW = NAN;        // mW
  float battery_voltage = NAN; // V (load voltage)

  double lat = 0.0;
  double lng = 0.0;
  uint32_t sats = 0;
  bool gps_valid = false;

  int wifi_rssi = 0;
  uint32_t free_heap = 0;
};
static Reading g_lastReading;

// ===================== UTILS =====================
static void yieldBrief() { delay(1); }

static bool isButtonPressedAtBoot() {
  pinMode(PIN_FORCE_PORTAL, INPUT_PULLUP);
  delay(10);
  return digitalRead(PIN_FORCE_PORTAL) == LOW;
}

static void safeStrCopy(char *dst, size_t cap, const char *src) {
  if (!dst || cap == 0)
    return;
  if (!src) {
    dst[0] = '\0';
    return;
  }
  strncpy(dst, src, cap - 1);
  dst[cap - 1] = '\0';
}

static void trimInPlace(char *s) {
  if (!s)
    return;
  size_t n = strlen(s);
  while (n > 0 && (s[n - 1] == ' ' || s[n - 1] == '\t' || s[n - 1] == '\r' ||
                   s[n - 1] == '\n')) {
    s[n - 1] = '\0';
    n--;
  }
  size_t i = 0;
  while (s[i] == ' ' || s[i] == '\t' || s[i] == '\r' || s[i] == '\n')
    i++;
  if (i > 0)
    memmove(s, s + i, strlen(s + i) + 1);
}

static void normalizeBaseUrlInPlace(char *url) {
  if (!url)
    return;
  trimInPlace(url);
  size_t n = strlen(url);
  while (n > 0 && url[n - 1] == '/') {
    url[n - 1] = '\0';
    n--;
  }
}

static uint32_t fnv1a32_update(uint32_t h, const void *data, size_t len) {
  const uint8_t *p = (const uint8_t *)data;
  for (size_t i = 0; i < len; i++) {
    h ^= p[i];
    h *= 16777619u;
  }
  return h;
}

// ===================== PREFS =====================
static void prefsLoad() {
  prefs.begin(PREF_NS, true);

  prefs.getString(KEY_SERVER_URL, g_serverUrl, sizeof(g_serverUrl));
  prefs.getString(KEY_DEVICE_ID, g_deviceId, sizeof(g_deviceId));
  prefs.getString(KEY_SECRET, g_sharedSecret, sizeof(g_sharedSecret));
  g_tlsInsecure = prefs.getBool(KEY_TLS_INSEC, true);

  g_oledEnabled = prefs.getBool(KEY_OLED_EN, true);
  g_oledFlip = (uint8_t)prefs.getUChar(KEY_OLED_FLIP, 0);
  g_oledContrast = (uint8_t)prefs.getUChar(KEY_OLED_CONTR, 255);
  g_oledAutoPage = prefs.getBool(KEY_OLED_AUTO, true);
  g_oledPage = (uint8_t)prefs.getUChar(KEY_OLED_PAGE, 0);
  g_oledIntervalMs = (uint32_t)prefs.getUInt(KEY_OLED_REF_MS, 100);
  g_oledPageIntervalMs = (uint32_t)prefs.getUInt(KEY_OLED_PG_MS, 5000);

  g_wifiEnabled = prefs.getBool(KEY_WIFI_EN, true);
  prefs.getString(KEY_WIFI_SSID, g_wifiSsid, sizeof(g_wifiSsid));
  prefs.getString(KEY_WIFI_PASS, g_wifiPass, sizeof(g_wifiPass));

  g_sensorReadPeriodMs = (uint32_t)prefs.getUInt(KEY_SENS_MS, 400);
  g_sensorIntervalSec = (uint32_t)prefs.getUInt(KEY_POST_SEC, 3);
  g_commandPollIntervalSec = (uint32_t)prefs.getUInt(KEY_CMD_SEC, 10);

  prefs.end();

  if (strlen(g_deviceId) == 0) {
    char tmpId[24];
    uint64_t m = ESP.getEfuseMac();
    snprintf(tmpId, sizeof(tmpId), "esp32-%06X", (uint32_t)(m & 0xFFFFFF));
    safeStrCopy(g_deviceId, sizeof(g_deviceId), tmpId);
  }

  // clamps
  if (g_oledFlip > 1)
    g_oledFlip = 0;
  if (g_oledPage >= OLED_PAGE_COUNT)
    g_oledPage = 0;
  if (g_oledContrast < 5)
    g_oledContrast = 5;
  if (g_oledIntervalMs < 50)
    g_oledIntervalMs = 50;
  if (g_oledIntervalMs > 2000)
    g_oledIntervalMs = 2000;
  if (g_oledPageIntervalMs < 800)
    g_oledPageIntervalMs = 800;
  if (g_oledPageIntervalMs > 20000)
    g_oledPageIntervalMs = 20000;
  if (g_sensorReadPeriodMs < 100)
    g_sensorReadPeriodMs = 100;
  if (g_sensorReadPeriodMs > 2000)
    g_sensorReadPeriodMs = 2000;
  if (g_sensorIntervalSec < 1)
    g_sensorIntervalSec = 1;
  if (g_sensorIntervalSec > 120)
    g_sensorIntervalSec = 120;
  if (g_commandPollIntervalSec < 3)
    g_commandPollIntervalSec = 3;
  if (g_commandPollIntervalSec > 300)
    g_commandPollIntervalSec = 300;

  normalizeBaseUrlInPlace(g_serverUrl);
  trimInPlace(g_deviceId);
  trimInPlace(g_sharedSecret);
}

static void prefsSave() {
  prefs.begin(PREF_NS, false);
  prefs.putString(KEY_SERVER_URL, g_serverUrl);
  prefs.putString(KEY_DEVICE_ID, g_deviceId);
  prefs.putString(KEY_SECRET, g_sharedSecret);
  prefs.putBool(KEY_TLS_INSEC, g_tlsInsecure);

  prefs.putBool(KEY_OLED_EN, g_oledEnabled);
  prefs.putUChar(KEY_OLED_FLIP, g_oledFlip);
  prefs.putUChar(KEY_OLED_CONTR, g_oledContrast);
  prefs.putBool(KEY_OLED_AUTO, g_oledAutoPage);
  prefs.putUChar(KEY_OLED_PAGE, g_oledPage);
  prefs.putUInt(KEY_OLED_REF_MS, g_oledIntervalMs);
  prefs.putUInt(KEY_OLED_PG_MS, g_oledPageIntervalMs);

  prefs.putBool(KEY_WIFI_EN, g_wifiEnabled);
  prefs.putString(KEY_WIFI_SSID, g_wifiSsid);
  prefs.putString(KEY_WIFI_PASS, g_wifiPass);

  prefs.putUInt(KEY_SENS_MS, g_sensorReadPeriodMs);
  prefs.putUInt(KEY_POST_SEC, g_sensorIntervalSec);
  prefs.putUInt(KEY_CMD_SEC, g_commandPollIntervalSec);

  prefs.end();
}
// ===================== URL PARSER =====================
static bool parseBaseUrl(const char *in, BaseUrl &out) {
  out = BaseUrl();
  if (!in || !in[0])
    return false;

  char tmp[200];
  safeStrCopy(tmp, sizeof(tmp), in);
  normalizeBaseUrlInPlace(tmp);

  const char *s = tmp;
  if (strncmp(s, "https://", 8) == 0) {
    out.https = true;
    s += 8;
  } else if (strncmp(s, "http://", 7) == 0) {
    out.https = false;
    s += 7;
  } else {
    out.https = false;
  }

  const char *slash = strchr(s, '/');
  char hostport[140] = {0};
  if (slash) {
    size_t hpLen = (size_t)(slash - s);
    if (hpLen >= sizeof(hostport))
      hpLen = sizeof(hostport) - 1;
    memcpy(hostport, s, hpLen);
    hostport[hpLen] = '\0';
    safeStrCopy(out.basePath, sizeof(out.basePath), slash);
  } else {
    safeStrCopy(hostport, sizeof(hostport), s);
    out.basePath[0] = '\0';
  }

  char *colon = strchr(hostport, ':');
  if (colon) {
    *colon = '\0';
    uint32_t p = (uint32_t)atoi(colon + 1);
    if (p == 0 || p > 65535)
      return false;
    out.port = (uint16_t)p;
  } else {
    out.port = out.https ? 443 : 80;
  }

  trimInPlace(hostport);
  if (strlen(hostport) == 0)
    return false;
  safeStrCopy(out.host, sizeof(out.host), hostport);

  normalizeBaseUrlInPlace(out.basePath);

  out.valid = true;
  return true;
}

static void rebuildParsedBase() {
  g_base.valid = false;
  if (strlen(g_serverUrl) == 0)
    return;
  if (!parseBaseUrl(g_serverUrl, g_base)) {
    Serial.println("[URL] Invalid server_url format");
    return;
  }
  Serial.printf("[URL] scheme=%s host=%s port=%u basePath=%s\n",
                g_base.https ? "https" : "http", g_base.host,
                (unsigned)g_base.port,
                g_base.basePath[0] ? g_base.basePath : "(none)");
}

// ===================== OFFLINE QUEUE =====================
static void offlinePush(const char *payload, uint16_t len) {
  if (!payload || len == 0)
    return;
  if (len >= OFFLINE_PAYLOAD_MAX)
    len = OFFLINE_PAYLOAD_MAX - 1;

  if (g_offlineCount >= OFFLINE_QUEUE_MAX) {
    g_offlineHead = (g_offlineHead + 1) % OFFLINE_QUEUE_MAX;
    g_offlineCount--;
  }

  memcpy(g_offlineBuf[g_offlineTail], payload, len);
  g_offlineBuf[g_offlineTail][len] = '\0';
  g_offlineLen[g_offlineTail] = len;

  g_offlineTail = (g_offlineTail + 1) % OFFLINE_QUEUE_MAX;
  g_offlineCount++;
}

static bool offlinePop(char *out, uint16_t &outLen) {
  if (g_offlineCount == 0)
    return false;
  uint8_t idx = g_offlineHead;

  outLen = g_offlineLen[idx];
  if (outLen >= OFFLINE_PAYLOAD_MAX)
    outLen = OFFLINE_PAYLOAD_MAX - 1;
  memcpy(out, g_offlineBuf[idx], outLen);
  out[outLen] = '\0';

  g_offlineHead = (g_offlineHead + 1) % OFFLINE_QUEUE_MAX;
  g_offlineCount--;
  return true;
}

// ===================== HMAC SIGNATURE =====================
static bool makeSignatureHex(char outHex[65], const char *method,
                             const char *path, const char *deviceId,
                             const uint8_t *body, size_t bodyLen) {
  outHex[0] = '\0';
  if (strlen(g_sharedSecret) == 0)
    return false;
  if (!method || !path || !deviceId)
    return false;

  unsigned char hmac[32];
  mbedtls_md_context_t ctx;
  const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);

  mbedtls_md_init(&ctx);
  if (mbedtls_md_setup(&ctx, info, 1) != 0) {
    mbedtls_md_free(&ctx);
    return false;
  }
  if (mbedtls_md_hmac_starts(&ctx, (const unsigned char *)g_sharedSecret,
                             strlen(g_sharedSecret)) != 0) {
    mbedtls_md_free(&ctx);
    return false;
  }

  mbedtls_md_hmac_update(&ctx, (const unsigned char *)method, strlen(method));
  mbedtls_md_hmac_update(&ctx, (const unsigned char *)" ", 1);
  mbedtls_md_hmac_update(&ctx, (const unsigned char *)path, strlen(path));
  mbedtls_md_hmac_update(&ctx, (const unsigned char *)"\n", 1);
  mbedtls_md_hmac_update(&ctx, (const unsigned char *)deviceId,
                         strlen(deviceId));
  mbedtls_md_hmac_update(&ctx, (const unsigned char *)"\n", 1);
  if (body && bodyLen > 0)
    mbedtls_md_hmac_update(&ctx, body, bodyLen);

  if (mbedtls_md_hmac_finish(&ctx, hmac) != 0) {
    mbedtls_md_free(&ctx);
    return false;
  }
  mbedtls_md_free(&ctx);

  static const char *hex = "0123456789abcdef";
  for (int i = 0; i < 32; i++) {
    outHex[i * 2] = hex[(hmac[i] >> 4) & 0xF];
    outHex[i * 2 + 1] = hex[hmac[i] & 0xF];
  }
  outHex[64] = '\0';
  return true;
}

// ===================== RAW HTTP HELPERS =====================
static size_t clientReadLine(Stream &s, char *line, size_t cap,
                             uint32_t timeoutMs) {
  if (!line || cap < 2)
    return 0;
  size_t n = 0;
  uint32_t start = millis();
  while ((millis() - start) < timeoutMs) {
    while (s.available()) {
      int c = s.read();
      if (c < 0)
        break;
      if (c == '\r')
        continue;
      if (c == '\n') {
        line[n] = '\0';
        return n;
      }
      if (n < cap - 1)
        line[n++] = (char)c;
    }
    delay(1);
  }
  line[n] = '\0';
  return n;
}

static int parseHttpStatus(const char *statusLine) {
  if (!statusLine)
    return -1;
  const char *sp = strchr(statusLine, ' ');
  if (!sp)
    return -1;
  while (*sp == ' ')
    sp++;
  int code = atoi(sp);
  return code > 0 ? code : -1;
}

static bool readHttpBody(WiFiClient &c, bool chunked, int contentLen, char *out,
                         size_t outCap, size_t &outLen) {
  outLen = 0;
  if (!out || outCap == 0)
    return false;

  if (chunked) {
    while (true) {
      char line[32];
      size_t ln = clientReadLine(c, line, sizeof(line), 8000);
      if (ln == 0)
        return false;
      uint32_t chunkSize = (uint32_t)strtoul(line, nullptr, 16);
      if (chunkSize == 0) {
        char tmp[64];
        while (true) {
          size_t x = clientReadLine(c, tmp, sizeof(tmp), 2000);
          if (x == 0)
            break;
          if (tmp[0] == '\0')
            break;
        }
        return true;
      }
      for (uint32_t i = 0; i < chunkSize; i++) {
        int ch = c.read();
        if (ch < 0) {
          uint32_t start = millis();
          while ((millis() - start) < 3000 && ch < 0) {
            delay(1);
            ch = c.read();
          }
          if (ch < 0)
            return false;
        }
        if (outLen + 1 < outCap)
          out[outLen++] = (char)ch;
      }
      (void)c.read();
      (void)c.read(); // CRLF
    }
  }

  if (contentLen >= 0) {
    int remaining = contentLen;
    while (remaining > 0) {
      while (!c.available()) {
        if (!c.connected())
          break;
        delay(1);
      }
      int ch = c.read();
      if (ch < 0) {
        if (!c.connected())
          break;
        continue;
      }
      if (outLen + 1 < outCap)
        out[outLen++] = (char)ch;
      remaining--;
    }
    return true;
  }

  uint32_t start = millis();
  while ((millis() - start) < 8000) {
    while (c.available()) {
      int ch = c.read();
      if (ch < 0)
        break;
      if (outLen + 1 < outCap)
        out[outLen++] = (char)ch;
      start = millis();
    }
    if (!c.connected())
      break;
    delay(1);
  }
  return true;
}

static bool httpRequest(const char *method, const char *pathOnly,
                        const uint8_t *body, size_t bodyLen,
                        const char *extraHeaderName,
                        const char *extraHeaderValue, int &outCode,
                        char *outBody, size_t outBodyCap, size_t &outBodyLen) {
  outCode = -1;
  outBodyLen = 0;
  if (!g_base.valid)
    return false;
  if (!method || !pathOnly)
    return false;

  char fullPath[200];
  if (g_base.basePath[0])
    snprintf(fullPath, sizeof(fullPath), "%s%s", g_base.basePath, pathOnly);
  else
    safeStrCopy(fullPath, sizeof(fullPath), pathOnly);

  WiFiClient plain;
  WiFiClientSecure secure;
  WiFiClient *client =
      g_base.https ? (WiFiClient *)&secure : (WiFiClient *)&plain;
  if (g_base.https && g_tlsInsecure)
    secure.setInsecure();
  client->setTimeout(12000);

  if (!client->connect(g_base.host, g_base.port))
    return false;

  client->printf("%s %s HTTP/1.1\r\n", method, fullPath);
  client->printf("Host: %s\r\n", g_base.host);
  client->print("User-Agent: esp32-weather-station\r\n");
  client->print("Accept: application/json\r\n");
  client->print("Accept-Encoding: identity\r\n");
  client->print("Connection: close\r\n");

  if (extraHeaderName && extraHeaderValue && extraHeaderName[0] &&
      extraHeaderValue[0]) {
    client->printf("%s: %s\r\n", extraHeaderName, extraHeaderValue);
  }

  if (body && bodyLen > 0 && strcmp(method, "POST") == 0) {
    client->print("Content-Type: application/json\r\n");
    client->printf("Content-Length: %u\r\n", (unsigned)bodyLen);
  }

  client->print("\r\n");
  if (body && bodyLen > 0 && strcmp(method, "POST") == 0)
    client->write(body, bodyLen);

  char line[256];
  size_t ln = clientReadLine(*client, line, sizeof(line), 8000);
  if (ln == 0) {
    client->stop();
    return false;
  }

  outCode = parseHttpStatus(line);
  if (outCode < 0) {
    client->stop();
    return false;
  }

  bool chunked = false;
  int contentLen = -1;

  while (true) {
    size_t h = clientReadLine(*client, line, sizeof(line), 8000);
    if (h == 0) {
      client->stop();
      return false;
    }
    if (line[0] == '\0')
      break;

    if (strncasecmp(line, "Transfer-Encoding:", 18) == 0) {
      if (strstr(line, "chunked") || strstr(line, "Chunked"))
        chunked = true;
    }
    if (strncasecmp(line, "Content-Length:", 15) == 0) {
      const char *p = line + 15;
      while (*p == ' ')
        p++;
      contentLen = atoi(p);
      if (contentLen < 0)
        contentLen = -1;
    }
  }

  bool okBody = true;
  if (outBody && outBodyCap > 0) {
    okBody = readHttpBody(*client, chunked, contentLen, outBody, outBodyCap,
                          outBodyLen);
    if (outBodyLen < outBodyCap)
      outBody[outBodyLen] = '\0';
    else
      outBody[outBodyCap - 1] = '\0';
  }

  client->stop();
  return okBody;
}

// ===================== I2C SCAN =====================
static void printI2CScan() {
  Serial.println();
  Serial.println(F("[I2C] Scanning..."));
  uint8_t count = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    uint8_t err = Wire.endTransmission();
    if (err == 0) {
      Serial.printf("[I2C] Found device at 0x%02X\n", addr);
      count++;
    }
  }
  if (count == 0)
    Serial.println(F("[I2C] No devices found"));
  Serial.println(F("[I2C] Scan done"));
}

// ===================== HASH CONFIG =====================
static uint32_t hashConfig(JsonObject payload) {
  uint32_t h = 2166136261u;

  int si = payload["sensor_interval"] | (int)g_sensorIntervalSec;
  h = fnv1a32_update(h, &si, sizeof(si));

  JsonObject cv = payload["calibration_values"].as<JsonObject>();
  if (!cv.isNull()) {
    float t = cv["temperature"] | g_calTemp;
    float rh = cv["humidity"] | g_calHum;
    int aq = cv["air_quality"] | g_calAir;
    float lx = cv["light_intensity"] | g_calLux;
    float bv = cv["battery_voltage"] | g_calVolt;

    h = fnv1a32_update(h, &t, sizeof(t));
    h = fnv1a32_update(h, &rh, sizeof(rh));
    h = fnv1a32_update(h, &aq, sizeof(aq));
    h = fnv1a32_update(h, &lx, sizeof(lx));
    h = fnv1a32_update(h, &bv, sizeof(bv));
  }

  JsonObject ss = payload["selected_sensors"].as<JsonObject>();
  if (!ss.isNull()) {
    bool gpsLat = ss["gps_latitude"] | true;
    bool gpsLng = ss["gps_longitude"] | true;
    bool cur = ss["current"] | true;
    bool vol = ss["voltage"] | true;
    bool pow = ss["power"] | true;

    uint8_t bits = 0;
    bits |= (gpsLat ? 1 : 0) << 0;
    bits |= (gpsLng ? 1 : 0) << 1;
    bits |= (cur ? 1 : 0) << 2;
    bits |= (vol ? 1 : 0) << 3;
    bits |= (pow ? 1 : 0) << 4;

    h = fnv1a32_update(h, &bits, sizeof(bits));
  }

  return h;
}

// ===================== OLED =====================
static String fmtFloat(float v, int decimals = 1) {
  if (!isfinite(v))
    return "N/A";
  return String(v, decimals);
}

static int getBattPct(float v) {
  if (!isfinite(v)) return 0;
  // Simple linear mapping for Li-ion 3.3V - 4.2V
  float p = (v - 3.4f) / (4.2f - 3.4f) * 100.0f;
  if (p < 0) p = 0; if (p > 100) p = 100;
  return (int)p;
}

// --- UI Global State for Scrolling ---
static int g_ssidScrollX = 0;
static uint32_t g_lastSsidScrollMs = 0;

static void oledDraw() {
  if (!g_oledEnabled)
    return;

  const uint32_t now = millis();
  // Auto-page switch (4 pages)
  if (g_oledAutoPage && (now - g_lastOledPageSwitchMs >= g_oledPageIntervalMs)) {
    g_oledPage = (uint8_t)((g_oledPage + 1) % 4);
    g_lastOledPageSwitchMs = now;
  }

  u8g2.setFlipMode(g_oledFlip);
  u8g2.setContrast(g_oledContrast);
  u8g2.clearBuffer();

  // ===================== HEADER/STATUS BAR (0-16px) =====================
  // Center Y for 16px header is 8.
  
  // 1. WiFi icon (16x14) - y=1 to center (1..15)
  int rssi = WiFi.isConnected() ? WiFi.RSSI() : -100;
  const uint8_t* wifiIcon = icon_wifi_0;
  if (rssi > -55) wifiIcon = icon_wifi_3;       
  else if (rssi > -70) wifiIcon = icon_wifi_2;  
  else if (rssi > -85) wifiIcon = icon_wifi_1;  
  u8g2.drawXBMP(0, 1, 16, 14, wifiIcon);

  // 2. SSID Scrolling Text
  u8g2.setFont(u8g2_font_5x7_tf);
  String ssid = WiFi.isConnected() ? WiFi.SSID() : "Nosignal";
  int ssidW = u8g2.getStrWidth(ssid.c_str());
  const int ssidBoxX = 18;
  const int ssidBoxW = 46; // Center area
  
  if (ssidW > ssidBoxW) {
    if (now - g_lastSsidScrollMs > 50) { 
      g_ssidScrollX--;
      if (g_ssidScrollX < -(ssidW + 15)) g_ssidScrollX = ssidBoxW;
      g_lastSsidScrollMs = now;
    }
    u8g2.setClipWindow(ssidBoxX, 0, ssidBoxX + ssidBoxW, 16);
    u8g2.drawStr(ssidBoxX + g_ssidScrollX, 11, ssid.c_str());
    u8g2.setMaxClipWindow();
  } else {
    int cx = ssidBoxX + (ssidBoxW - ssidW) / 2;
    u8g2.drawStr(cx, 11, ssid.c_str());
  }

  // 3. Server connection (20x12) - y=2 to center (2..14)
  u8g2.drawXBMP(66, 2, 20, 12, icon_server);
  if (!g_lastPostOk && (now % 1000 < 500)) {
    u8g2.drawLine(66, 2, 85, 14);
    u8g2.drawLine(85, 2, 66, 14);
  }

  // 4. Battery (18x10 including tip) - y=3 to center (3..13)
  const int batX = 98;
  const int batY = 3;
  const int batW = 18;
  const int batH = 10;
  
  u8g2.drawFrame(batX, batY, batW - 2, batH);
  u8g2.drawBox(batX + batW - 2, batY + 3, 2, 4);      
  
  int pct = getBattPct(g_lastReading.battery_voltage);
  int fillW = ((batW - 6) * pct) / 100;
  if (fillW > 12) fillW = 12;
  if (fillW < 0) fillW = 0;
  if (fillW > 0) u8g2.drawBox(batX + 2, batY + 2, fillW, batH - 4);

  if (isfinite(g_lastReading.current_mA) && g_lastReading.current_mA > 5.0f) {
    u8g2.setDrawColor(2); 
    u8g2.drawXBMP(batX + 5, batY + 0, 6, 10, icon_bolt_small);
    u8g2.setDrawColor(1);
  }
  
  u8g2.setFont(u8g2_font_4x6_tf);
  String pStr = String(pct) + "%";
  u8g2.drawStr(batX + (batW - u8g2.getStrWidth(pStr.c_str()))/2, 22, pStr.c_str());

  u8g2.drawHLine(0, 16, 128);

  // ===================== PAGE CONTENT =====================
  const int cY = 18; 

  switch (g_oledPage) {
    case 0: // PAGE 1: ENVIRONMENT
    {
      u8g2.drawXBMP(2, cY, 16, 16, icon_temp_16x16);
      u8g2.setFont(u8g2_font_6x12_tr);
      u8g2.setCursor(20, cY + 13);
      if (isfinite(g_lastReading.temperature)) {
        u8g2.print(g_lastReading.temperature, 1); u8g2.print("\260C"); 
      } else u8g2.print("--");

      u8g2.drawXBMP(66, cY, 16, 16, icon_air_16x16);
      u8g2.setCursor(84, cY + 13);
      u8g2.print(g_lastReading.air_quality);
      u8g2.setFont(u8g2_font_4x6_tf); u8g2.print(" ppm");

      const int row2Y = cY + 22;
      u8g2.drawXBMP(2, row2Y, 16, 16, icon_hum_16x16);
      u8g2.setFont(u8g2_font_6x12_tr);
      u8g2.setCursor(20, row2Y + 13);
      if (isfinite(g_lastReading.humidity)) {
        u8g2.print(g_lastReading.humidity, 1); u8g2.print("%");
      } else u8g2.print("--");

      u8g2.drawXBMP(66, row2Y, 16, 16, icon_sun_16x16);
      u8g2.setCursor(84, row2Y + 13);
      if (isfinite(g_lastReading.light_lux)) {
        float lx = g_lastReading.light_lux;
        if (lx > 9999) { u8g2.print((int)(lx/1000)); u8g2.print("k"); }
        else u8g2.print((int)lx);
      } else u8g2.print("--");
      u8g2.setFont(u8g2_font_4x6_tf); u8g2.print(" lux");
      break;
    }

    case 1: // PAGE 2: GPS
    {
      u8g2.setFont(u8g2_font_5x7_tf);
      int y = cY + 7;
      u8g2.drawStr(0, y, "GPS    : "); u8g2.print(g_lastReading.gps_valid ? "Fix" : "No Fix");
      
      y += 9; u8g2.drawStr(0, y, "Lat    : ");
      if (g_lastReading.gps_valid) u8g2.print(g_lastReading.lat, 6); else u8g2.print("-");
      
      y += 9; u8g2.drawStr(0, y, "Lng    : ");
      if (g_lastReading.gps_valid) u8g2.print(g_lastReading.lng, 6); else u8g2.print("-");
      
      y += 9; u8g2.drawStr(0, y, "Lokasi :");
      
      u8g2.setFont(u8g2_font_4x6_tf); 
      y += 7; u8g2.setCursor(0, y); u8g2.print("Jalan Sidotopo Lor I,");
      y += 7; u8g2.setCursor(0, y); u8g2.print("Surabaya, Jawa Timur");
      
      u8g2.drawXBMP(112, cY + 4, 16, 16, icon_pin_16x16);
      break;
    }

    case 2: // PAGE 3: POWER
    {
      u8g2.setFont(u8g2_font_6x12_tr);
      int y = cY + 12;
      u8g2.drawStr(0, y, "Tegangan : "); 
      if (isfinite(g_lastReading.bus_voltage)) {
        u8g2.print(g_lastReading.bus_voltage, 2); u8g2.print("V");
      } else u8g2.print("--");
      
      y += 14; u8g2.drawStr(0, y, "Arus     : "); 
      if (isfinite(g_lastReading.current_mA)) {
        u8g2.print(g_lastReading.current_mA, 0); u8g2.print("mA");
      } else u8g2.print("--");
      
      y += 14; u8g2.drawStr(0, y, "Daya     : "); 
      if (isfinite(g_lastReading.power_mW)) {
        u8g2.print(g_lastReading.power_mW, 0); u8g2.print("mW");
      } else u8g2.print("--");
      
      u8g2.drawXBMP(112, cY + 6, 16, 16, icon_light_16x16);
      break;
    }

    case 3: // PAGE 4: SYSTEM
    {
      u8g2.setFont(u8g2_font_5x7_tf);
      int y = cY + 8;
      u8g2.drawStr(0, y, "Web  : ws.ijuloss.my.id");
      
      y += 10; u8g2.drawStr(0, y, "IP   : ");
      if (WiFi.isConnected()) u8g2.print(WiFi.localIP().toString().c_str());
      else u8g2.print("Offline");
      
      y += 10; u8g2.drawStr(0, y, "HTTP : ");
       if (g_lastPostCode > 0) {
        u8g2.print(g_lastPostCode);
        if (g_lastPostCode == 200) u8g2.print(" OK");
        else if (g_lastPostCode == 500) u8g2.print(" Err");
       } else u8g2.print("---");
       
      u8g2.drawXBMP(108, cY + 4, 16, 16, icon_globe_16x16);
      break;
    }
  }

  u8g2.sendBuffer();
}

// ===================== SENSOR READ =====================
static int readMQ135Raw() {
  int raw = analogRead(PIN_MQ135_ADC);
  if (raw < 0)
    raw = 0;
  if (raw > 4095)
    raw = 4095;
  return raw;
}

static int mq135DerivedIndex(int raw) {
  float x = (float)raw / 4095.0f;
  return (int)lroundf(x * 500.0f);
}

static void readSensors(Reading &r) {
  r.free_heap = ESP.getFreeHeap();
  r.wifi_rssi = WiFi.isConnected() ? WiFi.RSSI() : 0;

  if (g_hasSHT31) {
    float t = sht31.readTemperature();
    float h = sht31.readHumidity();
    if (isfinite(t))
      r.temperature = t + g_calTemp;
    if (isfinite(h))
      r.humidity = h + g_calHum;
  }

  if (g_hasBH1750) {
    float lux = bh1750.readLightLevel();
    if (isfinite(lux))
      r.light_lux = lux + g_calLux;
  }

  if (g_hasINA219) {
    float busV = ina219.getBusVoltage_V();
    float shuntmV = ina219.getShuntVoltage_mV();
    float loadV = busV + (shuntmV / 1000.0f);

    float currentmA = ina219.getCurrent_mA();
    float powermW = ina219.getPower_mW();

    if (isfinite(busV))
      r.bus_voltage = busV;
    if (isfinite(currentmA))
      r.current_mA = currentmA;
    if (isfinite(powermW))
      r.power_mW = powermW;

    if (isfinite(loadV))
      r.battery_voltage = loadV + g_calVolt;
  }

  int raw = readMQ135Raw();
  r.air_quality_raw = raw;
  r.air_quality = mq135DerivedIndex(raw) + g_calAir;

  r.gps_valid = gps.location.isValid() && gps.location.age() < 5000;
  r.sats = gps.satellites.isValid() ? gps.satellites.value() : 0;
  if (r.gps_valid) {
    r.lat = gps.location.lat();
    r.lng = gps.location.lng();
  }
}

// ===================== PAYLOAD BUILD =====================
static size_t buildSensorPayloadToBuffer(const Reading &r) {
  g_docSend.clear();

  g_docSend["device_id"] = g_deviceId;
  g_docSend["firmware"] = FIRMWARE_VERSION;
  g_docSend["uptime_ms"] = (uint32_t)(millis() - g_bootMs);
  g_docSend["free_heap"] = r.free_heap;
  g_docSend["wifi_rssi"] = r.wifi_rssi;

  g_docSend["temperature"] = isfinite(r.temperature) ? r.temperature : 0.0f;
  g_docSend["humidity"] = isfinite(r.humidity) ? r.humidity : 0.0f;
  g_docSend["air_quality"] = r.air_quality;
  g_docSend["air_quality_raw"] = r.air_quality_raw;
  g_docSend["light_intensity"] = isfinite(r.light_lux) ? r.light_lux : 0.0f;

  g_docSend["battery_voltage"] =
      isfinite(r.battery_voltage) ? r.battery_voltage : 0.0f;

  // Optional (milli-units): keep in mA and mW to match your UI expectation
  if (g_hasINA219) {
    if (isfinite(r.current_mA))
      g_docSend["battery_current"] = r.current_mA;
    if (isfinite(r.power_mW))
      g_docSend["battery_power"] = r.power_mW;
  }

  // INA219 compatibility fields
  g_docSend["ina219_present"] = g_hasINA219 ? 1 : 0;

  if (g_selInaExtras && g_hasINA219) {
    if (isfinite(r.bus_voltage))
      g_docSend["voltage"] = r.bus_voltage; // bus voltage
    if (isfinite(r.current_mA)) {
      g_docSend["current_mA"] = r.current_mA;
      g_docSend["current"] = (float)(r.current_mA); // mA
    }
    if (isfinite(r.power_mW)) {
      g_docSend["power_mW"] = r.power_mW;
      g_docSend["power"] = (float)(r.power_mW); // mW
    }
  }

  // GPS fields
  if (g_selGps) {
    g_docSend["gps_valid"] = r.gps_valid;
    g_docSend["gps_sats"] = r.sats;
    if (r.gps_valid) {
      // Backend expects latitude/longitude (not gps_latitude/gps_longitude)
      g_docSend["latitude"] = r.lat;
      g_docSend["longitude"] = r.lng;
      // Keep legacy keys for sensor selection UI, harmless if ignored
      g_docSend["gps_latitude"] = r.lat;
      g_docSend["gps_longitude"] = r.lng;
    }
  }

  return serializeJson(g_docSend, g_payloadBuf, sizeof(g_payloadBuf));
}

// ===================== APPLY CONFIG =====================
static bool applyConfigFromJsonObject(JsonObject payload,
                                      const char *&reasonOut) {
  reasonOut = "";

  if (payload.containsKey("sensor_interval")) {
    int si = payload["sensor_interval"].as<int>();
    if (si < 1 || si > 60) {
      reasonOut = "sensor_interval out of range";
      return false;
    }
    g_sensorIntervalSec = (uint32_t)si;
  }

  if (payload.containsKey("selected_sensors")) {
    JsonObject ss = payload["selected_sensors"].as<JsonObject>();
    if (!ss.isNull()) {
      bool gpsLat = (bool)(ss["gps_latitude"] | true);
      bool gpsLng = (bool)(ss["gps_longitude"] | true);
      g_selGps = gpsLat || gpsLng;

      bool cur = (bool)(ss["current"] | true);
      bool vol = (bool)(ss["voltage"] | true);
      bool pow = (bool)(ss["power"] | true);
      g_selInaExtras = (cur || vol || pow);
    }
  }

  if (payload.containsKey("calibration_values")) {
    JsonObject cv = payload["calibration_values"].as<JsonObject>();
    if (!cv.isNull()) {
      if (cv.containsKey("temperature"))
        g_calTemp = cv["temperature"].as<float>();
      if (cv.containsKey("humidity"))
        g_calHum = cv["humidity"].as<float>();
      if (cv.containsKey("air_quality"))
        g_calAir = cv["air_quality"].as<int>();
      if (cv.containsKey("light_intensity"))
        g_calLux = cv["light_intensity"].as<float>();
      if (cv.containsKey("battery_voltage"))
        g_calVolt = cv["battery_voltage"].as<float>();
    }
  }

  return true;
}

// ===================== API CALLS =====================
static bool apiPost(const char *path, const uint8_t *body, size_t bodyLen,
                    const char *sigHexOrNull, int &code) {
  size_t respLen = 0;
  const char *hName = nullptr;
  const char *hVal = nullptr;
  if (sigHexOrNull && sigHexOrNull[0]) {
    hName = "X-Device-Signature";
    hVal = sigHexOrNull;
  }
  bool ok = httpRequest("POST", path, body, bodyLen, hName, hVal, code, nullptr,
                        0, respLen);
  return ok && (code >= 200 && code < 300);
}

static bool apiGetJson(const char *path, const char *sigHexOrNull,
                       JsonDocument &doc, int &code) {
  size_t respLen = 0;
  const char *hName = nullptr;
  const char *hVal = nullptr;
  if (sigHexOrNull && sigHexOrNull[0]) {
    hName = "X-Device-Signature";
    hVal = sigHexOrNull;
  }

  bool ok = httpRequest("GET", path, nullptr, 0, hName, hVal, code, g_respBuf,
                        sizeof(g_respBuf), respLen);
  if (!ok || !(code >= 200 && code < 300))
    return false;

  doc.clear();
  DeserializationError err = deserializeJson(doc, g_respBuf, respLen);
  if (err) {
    Serial.printf("[HTTP] JSON parse error: %s\n", err.c_str());
    return false;
  }
  return true;
}

static bool sendSensorPayloadSerialized(const char *json, size_t len) {
  if (!g_base.valid)
    return false;
  int code = 0;
  bool ok =
      apiPost("/api/sensor-data", (const uint8_t *)json, len, nullptr, code);
  g_lastPostCode = code;
  g_lastPostOk = ok;
  g_lastPostMs = millis();
  Serial.printf("[HTTP] POST /api/sensor-data code=%d ok=%d", code, ok ? 1 : 0);
  return ok;
}
static bool sendAckToServer(const char *commandId, bool success,
                            const char *reason) {
  if (!g_base.valid)
    return false;

  StaticJsonDocument<256> d;
  d["command_id"] = commandId ? commandId : "";
  d["success"] = success;
  d["reason"] = reason ? reason : "";

  char buf[256];
  size_t n = serializeJson(d, buf, sizeof(buf));

  char path[160];
  snprintf(path, sizeof(path), "/api/devices/%s/ack", g_deviceId);

  char sig[65] = {0};
  makeSignatureHex(sig, "POST", path, g_deviceId, (const uint8_t *)buf, n);

  int code = 0;
  bool ok =
      apiPost(path, (const uint8_t *)buf, n, sig[0] ? sig : nullptr, code);
  Serial.printf("[CMD] ACK code=%d ok=%d\n", code, ok ? 1 : 0);
  return ok;
}

static void pollDeviceCommands() {
  if (!WiFi.isConnected() || !g_base.valid)
    return;

  char path[170];
  snprintf(path, sizeof(path), "/api/devices/%s/commands", g_deviceId);

  char sig[65] = {0};
  makeSignatureHex(sig, "GET", path, g_deviceId, nullptr, 0);

  int code = 0;
  bool ok = apiGetJson(path, sig[0] ? sig : nullptr, g_docCmd, code);
  Serial.printf("[CMD] GET %s code=%d ok=%d\n", path, code, ok ? 1 : 0);

  if (code == 404) {
    g_forceLegacyConfig = true;
    g_forceLegacyUntilMs = millis() + 10UL * 60UL * 1000UL;
    Serial.println("[CMD] /api/devices/* not found -> legacy mode 10 min");
    return;
  }
  if (!ok)
    return;

  const char *cmd = g_docCmd["command"] | "no_command";
  if (strcmp(cmd, "apply_config") != 0)
    return;

  const char *cid = g_docCmd["command_id"] | "";
  JsonObject payload = g_docCmd["payload"].as<JsonObject>();
  if (strlen(cid) == 0 || payload.isNull()) {
    sendAckToServer(cid, false, "invalid command payload");
    return;
  }

  const char *reason = "";
  bool applied = applyConfigFromJsonObject(payload, reason);
  if (applied) {
    Serial.printf("[CMD] Applied config: interval=%us gps=%d inaExtras=%d\n",
                  (unsigned)g_sensorIntervalSec, g_selGps ? 1 : 0,
                  g_selInaExtras ? 1 : 0);
    sendAckToServer(cid, true, "");
  } else {
    Serial.printf("[CMD] Apply failed: %s\n", reason);
    sendAckToServer(cid, false, reason);
  }
}

static void pollLegacyConfig() {
  if (!WiFi.isConnected() || !g_base.valid)
    return;

  int code = 0;
  bool ok = apiGetJson("/api/esp32/config", nullptr, g_docLegacy, code);
  Serial.printf("[LEGACY] GET /api/esp32/config code=%d ok=%d\n", code,
                ok ? 1 : 0);
  if (!ok)
    return;

  JsonObject payload = g_docLegacy.as<JsonObject>();
  if (payload.isNull())
    return;

  uint32_t h = hashConfig(payload);
  if (h == g_lastCfgHash)
    return;

  const char *reason = "";
  bool applied = applyConfigFromJsonObject(payload, reason);
  if (applied) {
    g_lastCfgHash = h;
    Serial.printf("[LEGACY] Applied config: interval=%us gps=%d inaExtras=%d\n",
                  (unsigned)g_sensorIntervalSec, g_selGps ? 1 : 0,
                  g_selInaExtras ? 1 : 0);
  } else {
    Serial.printf("[LEGACY] Apply failed: %s\n", reason);
  }
}

static void pollAndApplyConfig() {
  if (g_forceLegacyConfig) {
    if ((int32_t)(millis() - g_forceLegacyUntilMs) < 0) {
      pollLegacyConfig();
      return;
    }
    g_forceLegacyConfig = false;
    Serial.println("[CMD] Legacy window ended -> try /api/devices/* again");
  }
  pollDeviceCommands();
  if (g_forceLegacyConfig)
    pollLegacyConfig();
}

static void flushOfflineQueue() {
  if (!WiFi.isConnected() || !g_base.valid)
    return;
  if (g_offlineCount == 0)
    return;

  uint8_t flushed = 0;
  while (g_offlineCount > 0 && flushed < 5) {
    uint16_t len = 0;
    char tmp[OFFLINE_PAYLOAD_MAX];
    if (!offlinePop(tmp, len))
      break;

    if (!sendSensorPayloadSerialized(tmp, len)) {
      offlinePush(tmp, len);
      break;
    }
    flushed++;
    yieldBrief();
  }
}

// ===================== WIFI =====================
static void ensureWiFiConnected() {
  // LED status always reflects current link
  digitalWrite(PIN_WIFI_LED, WiFi.isConnected() ? HIGH : LOW);

  // If WiFi is disabled by user setting, keep radio OFF.
  if (!g_wifiEnabled) {
    if (WiFi.getMode() != WIFI_OFF) {
      WiFi.disconnect(true, true);
      WiFi.mode(WIFI_OFF);
    }
    digitalWrite(PIN_WIFI_LED, LOW);
    return;
  }

  if (WiFi.isConnected())
    return;

  uint32_t now = millis();
  if (now - g_lastWiFiReconnectAttemptMs < WIFI_RECONNECT_COOLDOWN_MS)
    return;
  g_lastWiFiReconnectAttemptMs = now;

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  esp_wifi_set_ps(WIFI_PS_NONE);

  if (strlen(g_wifiSsid) > 0) {
    Serial.printf("[WiFi] Connecting (manual) SSID=%s\n", g_wifiSsid);
    WiFi.begin(g_wifiSsid, g_wifiPass);
  } else {
    Serial.println("[WiFi] Disconnected, attempting reconnect...");
    WiFi.reconnect();
  }
}

static void setupWiFiManager(bool forcePortal) {
  WiFi.mode(WIFI_STA);

  WiFi.setSleep(false);
  esp_wifi_set_ps(WIFI_PS_NONE);

  WiFiManager wm;
  wm.setConfigPortalTimeout(180);
  wm.setAPCallback(onAPMode);

  char serverBuf[160] = {0};
  char deviceBuf[64] = {0};
  char secretBuf[96] = {0};

  safeStrCopy(serverBuf, sizeof(serverBuf), g_serverUrl);
  safeStrCopy(deviceBuf, sizeof(deviceBuf), g_deviceId);
  safeStrCopy(secretBuf, sizeof(secretBuf), g_sharedSecret);

  WiFiManagerParameter p_server("server_url",
                                "Server Base URL (ex: http://ip:9999)",
                                serverBuf, sizeof(serverBuf));
  WiFiManagerParameter p_device("device_id", "Device ID (ex: esp32-1)",
                                deviceBuf, sizeof(deviceBuf));
  WiFiManagerParameter p_secret("secret", "Device Shared Secret (optional)",
                                secretBuf, sizeof(secretBuf));
  WiFiManagerParameter p_tls("tls_insec", "TLS Insecure (1=yes,0=no)",
                             g_tlsInsecure ? "1" : "0", 2);

  wm.addParameter(&p_server);
  wm.addParameter(&p_device);
  wm.addParameter(&p_secret);
  wm.addParameter(&p_tls);

  String apName = "WS-Setup";
  apName.toUpperCase();

  bool ok = false;
  if (forcePortal) {
    Serial.println("[WiFi] Forcing config portal...");
    ok = wm.startConfigPortal(apName.c_str(), PORTAL_PASS);
  } else {
    ok = wm.autoConnect(apName.c_str(), PORTAL_PASS);
  }

  safeStrCopy(g_serverUrl, sizeof(g_serverUrl), p_server.getValue());
  safeStrCopy(g_deviceId, sizeof(g_deviceId), p_device.getValue());
  safeStrCopy(g_sharedSecret, sizeof(g_sharedSecret), p_secret.getValue());

  normalizeBaseUrlInPlace(g_serverUrl);
  trimInPlace(g_deviceId);
  trimInPlace(g_sharedSecret);

  const char *tlsVal = p_tls.getValue();
  g_tlsInsecure =
      (tlsVal && (strcmp(tlsVal, "1") == 0 || strcasecmp(tlsVal, "true") == 0));

  if (strlen(g_deviceId) == 0)
    safeStrCopy(g_deviceId, sizeof(g_deviceId), "esp32-1");

  prefsSave();
  rebuildParsedBase();

  if (ok && WiFi.isConnected()) {
    digitalWrite(PIN_WIFI_LED, HIGH);
    Serial.printf("[WiFi] Connected. SSID=%s IP=%s\n", WiFi.SSID().c_str(),
                  WiFi.localIP().toString().c_str());
  } else {
    digitalWrite(PIN_WIFI_LED, LOW);
    Serial.println("[WiFi] Not connected (portal timeout or failed). Will keep "
                   "trying in background.");
  }
}

// ===================== WATCHDOG =====================
static void setupWatchdog() {
  g_wdtArmed = false;

#if ESP_IDF_VERSION_MAJOR >= 5
  // IDF v5 (ESP32 Arduino Core v3.x)
  esp_task_wdt_config_t cfg = {};
  cfg.timeout_ms = 10000;
  cfg.idle_core_mask = 0;
  cfg.trigger_panic = true;

  esp_err_t e = esp_task_wdt_init(&cfg);
  if (e != ESP_OK) {
    Serial.printf("[WDT] init failed: %d\n", (int)e);
    return;
  }

  e = esp_task_wdt_add(xTaskGetCurrentTaskHandle());
  if (e != ESP_OK) {
    Serial.printf("[WDT] add failed: %d\n", (int)e);
    return;
  }
#else
  // IDF v4 (ESP32 Arduino Core v2.x) uses seconds-based init.
  esp_err_t e = esp_task_wdt_init(10, true);
  if (e != ESP_OK) {
    Serial.printf("[WDT] init failed: %d\n", (int)e);
    return;
  }

  e = esp_task_wdt_add(NULL); // current task
  if (e != ESP_OK) {
    Serial.printf("[WDT] add failed: %d\n", (int)e);
    return;
  }
#endif

  g_wdtArmed = true;
  Serial.println("[WDT] armed");
}

static void feedWatchdog() {
  if (!g_wdtArmed)
    return;
  esp_err_t e = esp_task_wdt_reset();
  if (e != ESP_OK) {
    Serial.printf("[WDT] reset failed: %d (disarming)\n", (int)e);
    g_wdtArmed = false;
  }
}

// ===================== SETUP SENSORS =====================
static void setupSensors() {
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.setClock(400000);

  printI2CScan();

  u8g2.begin();
  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.clearBuffer();
  u8g2.drawStr(0, 12, "Booting...");
  u8g2.sendBuffer();

  g_hasSHT31 = sht31.begin(0x44);
  Serial.printf("[SHT31] %s\n", g_hasSHT31 ? "OK" : "NOT FOUND");

  g_hasBH1750 = bh1750.begin(BH1750::CONTINUOUS_HIGH_RES_MODE);
  Serial.printf("[BH1750] %s\n", g_hasBH1750 ? "OK" : "NOT FOUND");

  g_hasINA219 = ina219.begin();
  if (g_hasINA219)
    ina219.setCalibration_32V_2A();
  Serial.printf("[INA219] %s\n", g_hasINA219 ? "OK" : "NOT FOUND");

  analogReadResolution(12);
  analogSetPinAttenuation(PIN_MQ135_ADC, ADC_11db);
}

static void setupGPS() {
  GPS_Serial.begin(GPS_BAUD, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);
  Serial.printf("[GPS] UART2 baud=%u RX=%d TX=%d\n", (unsigned)GPS_BAUD,
                PIN_GPS_RX, PIN_GPS_TX);
}

static void loopGPS() {
  while (GPS_Serial.available() > 0)
    gps.encode(GPS_Serial.read());
}

// ===================== TASKS =====================
static void taskSendSensorDataIfDue() {
  const uint32_t now = millis();

  // 1) Periodic sensor read for OLED/serial (independent from POST rate)
  if (now - g_lastSensorReadMs >= g_sensorReadPeriodMs) {
    g_lastSensorReadMs = now;
    Reading r = g_lastReading;
    readSensors(r);
    g_lastReading = r;
  }

  // 2) Periodic POST to backend (seconds)
  const uint32_t postMs = g_sensorIntervalSec * 1000UL;
  if (now - g_lastSensorMs < postMs)
    return;
  g_lastSensorMs = now;

  const size_t n = buildSensorPayloadToBuffer(g_lastReading);
  if (n == 0)
    return;

  // If WiFi/server ready, try send; else queue offline
  if (g_wifiEnabled && WiFi.isConnected() && g_base.valid) {
    flushOfflineQueue();
    if (!sendSensorPayloadSerialized(g_payloadBuf, n))
      offlinePush(g_payloadBuf, (uint16_t)n);
  } else {
    // Mark an attempted send time for diagnostics even if offline
    g_lastPostOk = false;
    g_lastPostCode = 0;
    g_lastPostMs = now;
    offlinePush(g_payloadBuf, (uint16_t)n);
  }
}

static void taskPollConfigIfDue() {
  uint32_t now = millis();
  uint32_t intervalMs = g_commandPollIntervalSec * 1000UL;
  if (now - g_lastCmdMs < intervalMs)
    return;
  g_lastCmdMs = now;
  pollAndApplyConfig();
}

static void taskOledIfDue() {
  uint32_t now = millis();
  if (now - g_lastOledMs < g_oledIntervalMs)
    return;
  g_lastOledMs = now;
  oledDraw();
}

static void taskRealtimeSerialIfDue() {
  if (!g_rtEnabled)
    return;
  uint32_t now = millis();
  if (now - g_lastRtMs < 1000UL)
    return;
  g_lastRtMs = now;
  printStatusLine(g_lastReading);
}

// ===================== SERIAL =====================
static void printHelp() {
  Serial.println();
  Serial.println(F("=== Perintah (Serial) ==="));
  Serial.println(
      F("menu / help                      : tampilkan daftar perintah"));
  Serial.println(F("scan                             : I2C scan"));
  Serial.println(
      F("status                           : baca semua sensor sekali"));
  Serial.println(
      F("rt on / rt off                   : start/stop realtime serial 1 Hz"));
  Serial.println();
  Serial.println(
      F("oled on / oled off               : nyalakan/matikan refresh OLED"));
  Serial.println(F("oled flip 0|1|toggle             : orientasi OLED"));
  Serial.println(F("oled contrast <0-255>            : kontras OLED"));
  Serial.println(F("oled page auto                   : auto rotate page"));
  Serial.println(
      F("oled page <0-4>                  : pilih page manual (0..4)"));
  Serial.println(F("oled interval <ms>               : interval auto page"));
  Serial.println(F("oled refresh <ms>                : refresh OLED"));
  Serial.println(F("sensor interval <ms>             : interval update sensor "
                   "(OLED/serial)"));
  Serial.println(F("oled clear                       : clear OLED"));
  Serial.println(F("oled test <mode>|off             : "
                   "black|white|checker|grid|vstripes|hstripes|bars"));
  Serial.println();
  Serial.println(F("wifi on / wifi off               : enable/disable WiFi"));
  Serial.println(
      F("wifi set ssid=<..> pass=<..>     : set kredensial WiFi (disimpan)"));
  Serial.println(
      F("wifi clear                       : hapus SSID/PASS (manual)"));
  Serial.println(F("wifi status                      : status WiFi"));
  Serial.println();
  Serial.println(F("set server <baseUrl>             : set URL backend "
                   "(contoh: http://x:1111)"));
  Serial.println(F("set id <deviceId>                : set device_id"));
  Serial.println(
      F("set secret <sharedSecret>        : set shared secret (opsional)"));
  Serial.println(
      F("set tls <0|1>                    : TLS insecure (1) / verify (0)"));
  Serial.println(F("save                             : simpan semua setting"));
  Serial.println(F("load                             : muat semua setting"));
  Serial.println(
      F("portal                           : buka WiFiManager portal"));
  Serial.println(F("reboot                           : restart ESP32"));
  Serial.println();
}

static void i2cScan() {
  Serial.println(F("[I2C] Scanning..."));
  uint8_t count = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    uint8_t err = Wire.endTransmission();
    if (err == 0) {
      Serial.printf("  - Found 0x%02X\n", addr);
      count++;
    }
    delay(1);
  }
  Serial.printf("[I2C] Done. Found %u device(s).\n", (unsigned)count);
}

static void printStatusLine(const Reading &R) {
  Serial.print(F("SHT31D: "));
  if (g_hasSHT31 && isfinite(R.temperature) && isfinite(R.humidity)) {
    Serial.printf("%.2f C, %.1f %%RH", R.temperature, R.humidity);
  } else {
    Serial.print(F("ERR"));
  }

  Serial.print(F(" | BH1750: "));
  if (g_hasBH1750 && isfinite(R.light_lux))
    Serial.printf("%.1f lx", R.light_lux);
  else
    Serial.print(F("ERR"));

  Serial.print(F(" | INA219: "));
  if (g_hasINA219 && isfinite(R.bus_voltage) && isfinite(R.current_mA) &&
      isfinite(R.power_mW)) {
    Serial.printf("%.3f V, %.1f mA, %.1f mW", R.bus_voltage, R.current_mA,
                  R.power_mW);
  } else {
    Serial.print(F("ERR"));
  }

  Serial.print(F(" | MQ135: A="));
  Serial.print(R.air_quality_raw);
  Serial.print(F(" idx="));
  Serial.print(R.air_quality);

  Serial.print(F(" | GPS: "));
  if (g_selGps && R.gps_valid) {
    Serial.printf("OK sats=%u lat=%.6f lng=%.6f", (unsigned)R.sats, R.lat,
                  R.lng);
  } else if (g_selGps) {
    Serial.printf("NO sats=%u", (unsigned)R.sats);
  } else {
    Serial.print(F("DIS"));
  }

  Serial.print(F(" | WiFi: "));
  if (WiFi.isConnected())
    Serial.printf("%s %d dBm", WiFi.SSID().c_str(), WiFi.RSSI());
  else
    Serial.print(F("OFF"));

  Serial.print(F(" | Q="));
  Serial.print((unsigned)g_offlineCount);

  Serial.println();
}

static char g_serialLine[220];
static uint16_t g_serialLen = 0;

static bool readSerialLine(char *out, size_t cap) {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r')
      continue;
    if (c == '\n') {
      size_t n = (g_serialLen < cap - 1) ? g_serialLen : (cap - 1);
      memcpy(out, g_serialLine, n);
      out[n] = '\0';
      g_serialLen = 0;
      trimInPlace(out);
      return (out[0] != '\0');
    }
    if (g_serialLen < sizeof(g_serialLine) - 1)
      g_serialLine[g_serialLen++] = c;
  }
  return false;
}

static void handleSerial() {
  char cmd[220];
  if (!readSerialLine(cmd, sizeof(cmd)))
    return;

  // Aliases
  if (strcasecmp(cmd, "help") == 0 || strcasecmp(cmd, "menu") == 0) {
    printHelp();
    return;
  }

  // I2C scan
  if (strcasecmp(cmd, "scan") == 0) {
    i2cScan();
    return;
  }

  // One-shot status
  if (strcasecmp(cmd, "status") == 0) {
    Reading r = g_lastReading;
    readSensors(r);
    g_lastReading = r;
    printStatusLine(r);
    return;
  }

  // Realtime serial
  if (strncasecmp(cmd, "rt ", 3) == 0) {
    const char *v = cmd + 3;
    if (strcasecmp(v, "on") == 0) {
      g_rtEnabled = true;
      Serial.println(F("OK rt=on"));
      return;
    }
    if (strcasecmp(v, "off") == 0) {
      g_rtEnabled = false;
      Serial.println(F("OK rt=off"));
      return;
    }
    Serial.println(F("ERR use: rt on|off"));
    return;
  }

  // Sensor interval (ms)
  if (strncasecmp(cmd, "sensor interval ", 16) == 0) {
    long ms = atol(cmd + 16);
    if (ms < 200)
      ms = 200;
    if (ms > 60000)
      ms = 60000;
    g_sensorReadPeriodMs = (uint32_t)ms;
    prefsSave();
    Serial.printf("OK sensor_interval_ms=%lu\n",
                  (unsigned long)g_sensorReadPeriodMs);
    return;
  }

  // OLED commands
  if (strncasecmp(cmd, "oled ", 5) == 0) {
    const char *p = cmd + 5;

    if (strcasecmp(p, "on") == 0) {
      g_oledEnabled = true;
      prefsSave();
      Serial.println(F("OK oled=on"));
      return;
    }
    if (strcasecmp(p, "off") == 0) {
      g_oledEnabled = false;
      prefsSave();
      Serial.println(F("OK oled=off"));
      return;
    }

    if (strncasecmp(p, "flip ", 5) == 0) {
      const char *v = p + 5;
      if (strcasecmp(v, "toggle") == 0)
        g_oledFlip = g_oledFlip ? 0 : 1;
      else
        g_oledFlip = (uint8_t)(atoi(v) ? 1 : 0);
      u8g2.setFlipMode(g_oledFlip);
      prefsSave();
      Serial.printf("OK oled_flip=%u\n", (unsigned)g_oledFlip);
      return;
    }

    if (strncasecmp(p, "contrast ", 9) == 0) {
      long c = atol(p + 9);
      if (c < 0)
        c = 0;
      if (c > 255)
        c = 255;
      g_oledContrast = (uint8_t)c;
      u8g2.setContrast(g_oledContrast);
      prefsSave();
      Serial.printf("OK oled_contrast=%u\n", (unsigned)g_oledContrast);
      return;
    }

    if (strcasecmp(p, "page auto") == 0) {
      g_oledAutoPage = true;
      prefsSave();
      Serial.println(F("OK oled_page=auto"));
      return;
    }

    if (strncasecmp(p, "page ", 5) == 0) {
      int pg = atoi(p + 5);
      if (pg < 0)
        pg = 0;
      if (pg > 4)
        pg = 4;
      g_oledAutoPage = false;
      g_oledPage = (uint8_t)pg;
      prefsSave();
      Serial.printf("OK oled_page=%u\n", (unsigned)g_oledPage);
      return;
    }

    if (strncasecmp(p, "interval ", 9) == 0) {
      long ms = atol(p + 9);
      if (ms < 500)
        ms = 500;
      if (ms > 600000)
        ms = 600000;
      g_oledPageIntervalMs = (uint32_t)ms;
      prefsSave();
      Serial.printf("OK oled_interval_ms=%lu\n",
                    (unsigned long)g_oledPageIntervalMs);
      return;
    }

    if (strncasecmp(p, "refresh ", 8) == 0) {
      long ms = atol(p + 8);
      if (ms < 100)
        ms = 100;
      if (ms > 60000)
        ms = 60000;
      g_oledIntervalMs = (uint32_t)ms;
      prefsSave();
      Serial.printf("OK oled_refresh_ms=%lu\n",
                    (unsigned long)g_oledIntervalMs);
      return;
    }

    if (strcasecmp(p, "clear") == 0) {
      u8g2.clearBuffer();
      u8g2.sendBuffer();
      Serial.println(F("OK oled_clear"));
      return;
    }

    if (strncasecmp(p, "test ", 5) == 0) {
      const char *v = p + 5;
      if (strcasecmp(v, "off") == 0) {
        g_oledTestMode = 0;
        Serial.println(F("OK oled_test=off"));
        return;
      }
      if (strcasecmp(v, "black") == 0)
        g_oledTestMode = 1;
      else if (strcasecmp(v, "white") == 0)
        g_oledTestMode = 2;
      else if (strcasecmp(v, "checker") == 0)
        g_oledTestMode = 3;
      else if (strcasecmp(v, "grid") == 0)
        g_oledTestMode = 4;
      else if (strcasecmp(v, "vstripes") == 0)
        g_oledTestMode = 5;
      else if (strcasecmp(v, "hstripes") == 0)
        g_oledTestMode = 6;
      else if (strcasecmp(v, "bars") == 0)
        g_oledTestMode = 7;
      else {
        Serial.println(
            F("ERR mode: black|white|checker|grid|vstripes|hstripes|bars|off"));
        return;
      }
      Serial.printf("OK oled_test=%u\n", (unsigned)g_oledTestMode);
      return;
    }

    Serial.println(F("ERR oled cmd"));
    return;
  }

  // WiFi commands
  if (strncasecmp(cmd, "wifi ", 5) == 0) {
    const char *p = cmd + 5;

    if (strcasecmp(p, "on") == 0) {
      g_wifiEnabled = true;
      prefsSave();
      WiFi.mode(WIFI_STA);
      WiFi.setSleep(false);
      esp_wifi_set_ps(WIFI_PS_NONE);
      if (strlen(g_wifiSsid) > 0)
        WiFi.begin(g_wifiSsid, g_wifiPass);
      else
        WiFi.reconnect();
      Serial.println(F("OK wifi=on"));
      return;
    }

    if (strcasecmp(p, "off") == 0) {
      g_wifiEnabled = false;
      prefsSave();
      WiFi.disconnect(true, true);
      WiFi.mode(WIFI_OFF);
      digitalWrite(PIN_WIFI_LED, LOW);
      Serial.println(F("OK wifi=off"));
      return;
    }

    if (strncasecmp(p, "set ", 4) == 0) {
      // Format: wifi set ssid=<..> pass=<..>
      const char *kv = p + 4;
      const char *ss = strstr(kv, "ssid=");
      const char *pa = strstr(kv, "pass=");
      if (!ss) {
        Serial.println(F("ERR wifi set needs ssid=<..>"));
        return;
      }
      char ssid[33] = {0};
      char pass[65] = {0};

      // parse ssid value
      ss += 5;
      const char *ss_end = strchr(ss, ' ');
      size_t ss_len = ss_end ? (size_t)(ss_end - ss) : strlen(ss);
      if (ss_len >= sizeof(ssid))
        ss_len = sizeof(ssid) - 1;
      memcpy(ssid, ss, ss_len);
      ssid[ss_len] = '\0';

      if (pa) {
        pa += 5;
        const char *pa_end = strchr(pa, ' ');
        size_t pa_len = pa_end ? (size_t)(pa_end - pa) : strlen(pa);
        if (pa_len >= sizeof(pass))
          pa_len = sizeof(pass) - 1;
        memcpy(pass, pa, pa_len);
        pass[pa_len] = '\0';
      }

      safeStrCopy(g_wifiSsid, sizeof(g_wifiSsid), ssid);
      safeStrCopy(g_wifiPass, sizeof(g_wifiPass), pass);
      g_wifiEnabled = true;
      prefsSave();

      WiFi.mode(WIFI_STA);
      WiFi.setSleep(false);
      esp_wifi_set_ps(WIFI_PS_NONE);
      WiFi.disconnect(true, true);
      delay(50);
      WiFi.begin(g_wifiSsid, g_wifiPass);

      Serial.printf("OK wifi_ssid=%s\n", g_wifiSsid);
      return;
    }

    if (strcasecmp(p, "clear") == 0) {
      g_wifiSsid[0] = '\0';
      g_wifiPass[0] = '\0';
      prefsSave();
      Serial.println(F("OK wifi_clear"));
      return;
    }

    if (strcasecmp(p, "status") == 0) {
      Serial.printf("wifi_enabled=%d\n", g_wifiEnabled ? 1 : 0);
      Serial.printf("manual_ssid=%s\n",
                    strlen(g_wifiSsid) ? g_wifiSsid : "(none)");
      Serial.printf("connected=%d\n", WiFi.isConnected() ? 1 : 0);
      if (WiFi.isConnected()) {
        Serial.printf("ssid=%s\n", WiFi.SSID().c_str());
        Serial.printf("ip=%s\n", WiFi.localIP().toString().c_str());
        Serial.printf("rssi=%d\n", WiFi.RSSI());
      }
      return;
    }

    Serial.println(F("ERR wifi cmd"));
    return;
  }

  // Config / backend
  if (strcasecmp(cmd, "save") == 0) {
    prefsSave();
    Serial.println(F("OK saved"));
    return;
  }
  if (strcasecmp(cmd, "load") == 0) {
    prefsLoad();
    rebuildParsedBase();
    Serial.println(F("OK loaded"));
    return;
  }

  if (strcasecmp(cmd, "portal") == 0) {
    setupWiFiManager(true);
    return;
  }
  if (strcasecmp(cmd, "reboot") == 0) {
    Serial.println(F("Rebooting..."));
    delay(200);
    ESP.restart();
  }

  // Existing minimal config commands kept for compatibility
  if (strcasecmp(cmd, "show") == 0) {
    Serial.printf("server_url=%s\n", g_serverUrl);
    Serial.printf("device_id=%s\n", g_deviceId);
    Serial.printf("secret_set=%d\n", strlen(g_sharedSecret) > 0 ? 1 : 0);
    Serial.printf("tls_insecure=%d\n", g_tlsInsecure ? 1 : 0);
    Serial.printf("post_interval_s=%us\n", (unsigned)g_sensorIntervalSec);
    Serial.printf("sensor_interval_ms=%lu\n",
                  (unsigned long)g_sensorReadPeriodMs);
    Serial.printf("queue=%u\n", (unsigned)g_offlineCount);
    Serial.printf("free_heap=%u\n", (unsigned)ESP.getFreeHeap());
    Serial.printf("legacy_mode=%d\n", g_forceLegacyConfig ? 1 : 0);
    Serial.printf("gps_enabled=%d ina_extras=%d ina219_present=%d\n",
                  g_selGps ? 1 : 0, g_selInaExtras ? 1 : 0,
                  g_hasINA219 ? 1 : 0);
    return;
  }

  if (strncasecmp(cmd, "set server ", 11) == 0) {
    safeStrCopy(g_serverUrl, sizeof(g_serverUrl), cmd + 11);
    normalizeBaseUrlInPlace(g_serverUrl);
    prefsSave();
    rebuildParsedBase();
    Serial.printf("OK server_url=%s\n", g_serverUrl);
    return;
  }

  if (strncasecmp(cmd, "set id ", 7) == 0) {
    safeStrCopy(g_deviceId, sizeof(g_deviceId), cmd + 7);
    trimInPlace(g_deviceId);
    if (strlen(g_deviceId) == 0)
      safeStrCopy(g_deviceId, sizeof(g_deviceId), "esp32-1");
    prefsSave();
    Serial.printf("OK device_id=%s\n", g_deviceId);
    return;
  }

  if (strncasecmp(cmd, "set secret ", 11) == 0) {
    safeStrCopy(g_sharedSecret, sizeof(g_sharedSecret), cmd + 11);
    trimInPlace(g_sharedSecret);
    prefsSave();
    Serial.printf("OK secret_set=%d\n", strlen(g_sharedSecret) > 0 ? 1 : 0);
    return;
  }

  if (strncasecmp(cmd, "set tls ", 8) == 0) {
    int v = atoi(cmd + 8);
    g_tlsInsecure = (v != 0);
    prefsSave();
    Serial.printf("OK tls_insecure=%d\n", g_tlsInsecure ? 1 : 0);
    return;
  }

  Serial.println(F("ERR unknown. Ketik: help"));
}

// ===================== ARDUINO =====================
void setup() {
  Serial.begin(115200);
  delay(50);

  pinMode(PIN_WIFI_LED, OUTPUT);
  digitalWrite(PIN_WIFI_LED, LOW);

  g_bootMs = millis();

  prefsLoad();
  rebuildParsedBase();

  Serial.println();
  Serial.println("=== ESP32 Weather Station (Unified SSD1306) ===");
  Serial.printf("Firmware: %s\n", FIRMWARE_VERSION);
  Serial.printf("Device ID: %s\n", g_deviceId);
  Serial.printf("Server URL: %s\n", g_serverUrl);
  Serial.printf("TLS insecure: %d\n", g_tlsInsecure ? 1 : 0);
  Serial.printf("Default sensors: gps=%d ina_extras=%d\n", g_selGps ? 1 : 0,
                g_selInaExtras ? 1 : 0);

  WiFi.setSleep(false);
  esp_wifi_set_ps(WIFI_PS_NONE);

  setupWatchdog();
  setupSensors();
  setupGPS();

  bool forcePortal = isButtonPressedAtBoot();
  if (!g_wifiEnabled && !forcePortal) {
    WiFi.mode(WIFI_OFF);
    digitalWrite(PIN_WIFI_LED, LOW);
    Serial.println(
        "[WiFi] Disabled by setting (wifi off). Use: wifi on / portal");
  } else {
    setupWiFiManager(forcePortal);
  }

  printHelp();
}

void loop() {
  feedWatchdog();

  loopGPS();
  ensureWiFiConnected();

  taskSendSensorDataIfDue();
  taskPollConfigIfDue();
  taskOledIfDue();
  taskRealtimeSerialIfDue();

  handleSerial();

  yieldBrief();
}
