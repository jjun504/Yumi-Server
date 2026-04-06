#include <WiFi.h>
#include <PubSubClient.h>

#define RAIN_SENSOR_PIN 32  // 雨滴传感器 DO 接 GPIO32

const char *ssid = "Green Apples";
const char *password = "GreenApple3249";

String mqtt_ClientID = "smart_assistant_87";

// Topics from water_sensor.ino
const char* pub_init_topic_water = "smart187/yumi_esp32s_water_sensor/is_back";
const char* sub_rain_topic = "smart187/yumi_esp32s_water_sensor/ack";
const char* pub_rain_topic = "smart187/yumi_esp32s_water_sensor/control";


const char *mqtt_server = "broker.emqx.io";
const char *mqtt_userName = "smart_assistant";
const char *mqtt_password = "alivetoA+";

WiFiClient espClient;
PubSubClient client(espClient);

bool lastRainState = false;

void setup_wifi() {
    delay(10);
    Serial.println();
    Serial.print("Connecting to ");
    Serial.println(ssid);

    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    randomSeed(micros());

    Serial.println();
    Serial.println("WiFi connected");
    Serial.println("IP address: ");
    Serial.println(WiFi.localIP());
}

void reconnect() {
    while (!client.connected()) {
        Serial.println("Attempting EMQX MQTT connection...");
        String clientId = mqtt_ClientID + String(random(0xffff), HEX);  // Avoid ID conflicts
        if (client.connect(clientId.c_str(), mqtt_userName, mqtt_password)) {
            Serial.print("Connected with Client ID: ");
            Serial.println(clientId);
            client.publish(pub_init_topic, "Hi, I'm online!");
            client.publish(pub_init_topic_water, "Hi, I'm online!");
            client.subscribe(sub_topic);
        } else {
            Serial.print("failed, rc=");
            Serial.print(client.state());
            Serial.println(" try again in 5 seconds");
            delay(5000);
        }
    }
}

void setup() {
    pinMode(RAIN_SENSOR_PIN, INPUT);
    Serial.begin(115200);
    setup_wifi();
    client.setServer(mqtt_server, 1883);
}

void loop() {
    if (!client.connected()) {
        reconnect();
    }
    client.loop();

    bool currentRainState = digitalRead(RAIN_SENSOR_PIN) == LOW;  // LOW 表示有雨滴

    if (currentRainState != lastRainState) {
        lastRainState = currentRainState;
        if (currentRainState) {
            Serial.println("Rain detected!");
            client.publish(pub_rain_topic, "Rain detected");
        } else {
            Serial.println("No rain.");
            client.publish(pub_rain_topic, "No rain");
        }
    }

    delay(500);  // 可调整检测频率
}
