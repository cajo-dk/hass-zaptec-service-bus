# Zaptec StateId Reference (Zaptec Go)

This document maps commonly exposed **StateIds** from the Zaptec `/chargers/{id}/state` endpoint to their meanings.

---

## 🔌 Connection / Charging State

| StateId | Name                 | Description                   |
| ------- | -------------------- | ----------------------------- |
| **710** | ChargerOperationMode | Charger state machine         |
|         | 1                    | Disconnected                  |
|         | 2                    | Connected – requesting charge |
|         | 3                    | Charging                      |
|         | 5                    | Connected – finished / idle   |

👉 Use this as the **primary indicator of whether the car is plugged in**

---

## ⚡ Power & Energy

| StateId | Name             | Unit | Description                             |
| ------- | ---------------- | ---- | --------------------------------------- |
| **513** | TotalChargePower | W    | Instantaneous total power               |
| **553** | SessionEnergy    | kWh  | Energy delivered during current session |
| **270** | TotalEnergy      | kWh  | Lifetime energy meter                   |

---

## 🔌 Voltage

| StateId | Name          | Unit |
| ------- | ------------- | ---- |
| **501** | VoltagePhase1 | V    |
| **502** | VoltagePhase2 | V    |
| **503** | VoltagePhase3 | V    |

---

## 🔋 Current

| StateId | Name          | Unit |
| ------- | ------------- | ---- |
| **507** | CurrentPhase1 | A    |
| **508** | CurrentPhase2 | A    |
| **509** | CurrentPhase3 | A    |

---

## 🧠 Charger Limits & Configuration

| StateId | Name             | Unit | Description             |
| ------- | ---------------- | ---- | ----------------------- |
| **510** | MaxCurrent       | A    | Hardware limit          |
| **511** | MinCurrent       | A    | Minimum allowed current |
| **708** | AvailableCurrent | A    | Allowed current         |
| **702** | ChargingCurrent  | A    | Actual charging current |

---

## 🔌 Electrical Installation

| StateId | Name              | Description             |
| ------- | ----------------- | ----------------------- |
| **519** | Phases            | Connected phases        |
| **520** | PhaseMode         | 1-phase / 3-phase setup |
| **522** | FuseSize          | Installation fuse       |
| **523** | CableCurrentLimit | Cable capability        |

---

## 🔐 Session Information

| StateId | Name          | Description             |
| ------- | ------------- | ----------------------- |
| **723** | LastSession   | Signed session metadata |
| **554** | MeterReading  | MID/OCMF meter data     |
| **751** | UptimeSeconds | Runtime counter         |

---

## 🌡️ Temperature

| StateId | Name           |
| ------- | -------------- |
| **201** | InternalTemp   |
| **202** | ExternalTemp   |
| **204** | PowerBoardTemp |
| **206** | MCU Temp       |
| **207** | Ambient Temp   |
| **220** | Connector Temp |

---

## 🌐 Connectivity

| StateId | Name           |
| ------- | -------------- |
| **150** | ActiveNetwork  |
| **151** | Online         |
| **808** | DebugStatus    |
| **809** | SignalStrength |

---

## ⚙️ Device Information

| StateId | Name            |
| ------- | --------------- |
| **100** | DeviceInfo      |
| **157** | IoT Hub         |
| **158** | IoT Device ID   |
| **160** | Profile         |
| **800** | InstallationId  |
| **801** | ChargerGroup    |
| **802** | SerialNumber    |
| **908** | FirmwareVersion |
| **911** | ChargerFW       |
| **916** | PlatformVersion |

---

## 🧯 Safety & Protection

| StateId     | Name                       |
| ----------- | -------------------------- |
| **718**     | RCD Trip Status            |
| **712**     | Lock Status                |
| **711**     | Authentication Enabled     |
| **545–548** | Internal protection limits |

---

## 🟢 Practical Interpretation

| Situation       | 710 | 513 |
| --------------- | --- | --- |
| Unplugged       | 1   | 0   |
| Plugged waiting | 2   | 0   |
| Charging        | 3   | >0  |
| Finished        | 5   | 0   |

---

## 🧭 Useful HA Logic

| State                      | Logic                   |
| -------------------------- | ----------------------- |
| Plugged in                 | `710 != 1`              |
| Charging                   | `710 == 3` OR `513 > 0` |
| Waiting for smart charging | `710 == 2`              |
| Active power               | `513`                   |
| Session energy             | `553`                   |
