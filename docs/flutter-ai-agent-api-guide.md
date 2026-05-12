# FasalX Flutter AI Agent API Integration Guide

This guide is for the frontend owner or AI coding agent connecting the Flutter app in `frontend_client/` to the FastAPI services in this repository. It documents the current backend API surface module-wise, then gives a step-by-step Flutter setup and integration plan.

Last verified from source code on 2026-05-12.

## 1. Service Map

FasalX is split into multiple FastAPI apps. Do not assume every endpoint lives behind one port.

| Service | Local Docker port | App module | Main responsibility | Flutter should call directly? |
|---|---:|---|---|---|
| Main backend | `8000` | `backend/app/main.py` | Firebase auth, users, chatbot, disease proxy, agronomy, geo, fields, telemetry, dashboard config, admin config | Yes |
| Timeline service | `8001` | `timeline_service/app/main.py` | Crop lifecycle timeline and GDD recalibration | Yes, until routed through main backend |
| Recommendation engine | `8002` | `backend/app/recommendation_main.py` | Field intelligence, crop recommendation, disease proxy duplicate | Yes for recommendation and field intelligence |
| ML disease service | internal `8003` | `ML_fasalX/main.py` | TensorFlow crop disease inference | Usually no; call `/api/v1/disease/predict` on main backend |
| Redis | `6379` | Docker service | Caching and Arq queue | No |
| MongoDB | `27017` | Docker service | Persistence | No |

Recommended Flutter base URLs:

```dart
class ApiBases {
  static const auth = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );

  static const timeline = String.fromEnvironment(
    'TIMELINE_API_BASE_URL',
    defaultValue: 'http://localhost:8001/api/v1',
  );

  static const recommend = String.fromEnvironment(
    'RECOMMENDATION_API_BASE_URL',
    defaultValue: 'http://localhost:8002/api/v1',
  );
}
```

Device-specific localhost rules:

| Flutter target | Backend host to use |
|---|---|
| Flutter web on same machine | `http://localhost:8000` |
| Windows/macOS/Linux desktop | `http://localhost:8000` |
| Android emulator | `http://10.0.2.2:8000` |
| iOS simulator | `http://localhost:8000` |
| Physical phone | `http://<your-laptop-LAN-IP>:8000` |
| Docker Compose Flutter web container | `http://fasalx-auth:8000` inside Docker, or expose through host config |

## 2. Backend Startup For Frontend Work

From the repository root:

```powershell
docker compose up --build fasalx-auth fasalx-timeline recommendation-engine redis mongodb ml-service
```

Useful health checks:

```text
GET http://localhost:8000/health
GET http://localhost:8001/health
GET http://localhost:8002/health
```

FastAPI docs:

```text
http://localhost:8000/docs
http://localhost:8001/docs
http://localhost:8002/docs
```

The docs UI is installed by the local docs helper, while `/openapi.json` remains useful for generated clients.

## 3. Authentication Model

Most main backend endpoints use Firebase ID tokens through `Authorization: Bearer <firebaseIdToken>`.

Frontend login sequence:

1. User signs in with Firebase in Flutter.
2. Flutter gets a fresh Firebase ID token.
3. Flutter calls `POST /api/v1/users/sync`.
4. Flutter stores no backend password or custom token. It only asks Firebase for refreshed ID tokens.
5. All protected API calls include the ID token in the `Authorization` header.

Dio interceptor pattern:

```dart
class FirebaseAuthInterceptor extends Interceptor {
  FirebaseAuthInterceptor(this.auth);

  final FirebaseAuth auth;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    final user = auth.currentUser;
    final token = await user?.getIdToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    options.headers['Accept'] = 'application/json';
    handler.next(options);
  }
}
```

Admin endpoints require Firebase custom claims. The backend trusts claims such as `admin`, `super_admin`, `role`, `roles`, `permissions`, or `admin_permissions`, then checks the permission required by the route.

Current important auth notes from source:

| Area | Auth behavior today |
|---|---|
| `/api/v1/users/*` | Firebase user token required |
| `/api/v1/admin/*` | Firebase admin/super_admin custom claims required |
| `/api/v1/chatbot/*` | Firebase user token required |
| `/api/v1/disease/predict` | Firebase user token required |
| `/api/v1/agronomy/*` | Firebase user token required |
| `/api/v1/fields/*` | Firebase user token required |
| `/api/v1/telemetry/data` | Firebase user token required |
| `/api/v1/dashboard/visibility` | Public |
| `/api/v1/geo/` | Public |
| Timeline endpoints | Auth currently bypassed in route code for frontend development |
| Recommendation `/calculate` and `/select` | Firebase user token required |
| Recommendation `/ingest/` | Public in current code |

## 4. Flutter Setup Procedure

### Step 1. Confirm Flutter project dependencies

The current `frontend_client/pubspec.yaml` already includes:

```yaml
dio: ^5.9.2
flutter_riverpod: ^3.3.1
get_it: ^9.2.1
shared_preferences: ^2.5.5
intl: ^0.20.2
```

Add Firebase dependencies if authentication is not wired yet:

```powershell
cd frontend_client
flutter pub add firebase_core firebase_auth
flutter pub get
```

### Step 2. Configure Firebase

Use the FlutterFire CLI or your existing Firebase files:

```powershell
dart pub global activate flutterfire_cli
flutterfire configure
```

Then initialize Firebase before `runApp`:

```dart
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );
  await setupServiceLocator();
  runApp(const ProviderScope(child: FasalXApp()));
}
```

### Step 3. Split API clients by service

The existing service locator registers one `Dio` with `AppConfig.apiBaseUrl`. Keep that for main backend, but add named clients for timeline and recommendation to avoid hardcoded URLs inside repositories.

```dart
getIt.registerLazySingleton<Dio>(
  () => buildDio(ApiBases.auth),
  instanceName: 'authApi',
);

getIt.registerLazySingleton<Dio>(
  () => buildDio(ApiBases.timeline),
  instanceName: 'timelineApi',
);

getIt.registerLazySingleton<Dio>(
  () => buildDio(ApiBases.recommend),
  instanceName: 'recommendApi',
);

Dio buildDio(String baseUrl) {
  final dio = Dio(
    BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
      sendTimeout: const Duration(seconds: 30),
    ),
  );
  dio.interceptors.add(FirebaseAuthInterceptor(FirebaseAuth.instance));
  dio.interceptors.add(LogInterceptor(requestBody: true, responseBody: true));
  return dio;
}
```

### Step 4. Create a common API result layer

FastAPI validation errors return `422`. Custom app errors usually return:

```json
{
  "success": false,
  "detail": "Human-readable message",
  "error": {
    "code": "TOKEN_EXPIRED",
    "message": "Token has expired. Please reauthenticate."
  }
}
```

Use one mapper for all repositories:

```dart
class ApiFailure implements Exception {
  ApiFailure(this.message, {this.code, this.statusCode});

  final String message;
  final String? code;
  final int? statusCode;

  factory ApiFailure.fromDio(DioException error) {
    final data = error.response?.data;
    if (data is Map<String, dynamic>) {
      final nested = data['error'];
      return ApiFailure(
        data['detail']?.toString() ??
            (nested is Map ? nested['message']?.toString() : null) ??
            error.message ??
            'Request failed',
        code: nested is Map ? nested['code']?.toString() : null,
        statusCode: error.response?.statusCode,
      );
    }
    return ApiFailure(error.message ?? 'Network error', statusCode: error.response?.statusCode);
  }
}
```

### Step 5. Recommended frontend module structure

```text
lib/
  core/
    config/
      app_config.dart
      api_bases.dart
    network/
      api_failure.dart
      dio_factory.dart
      firebase_auth_interceptor.dart
  features/
    auth/
    dashboard/
    chatbot/
    disease/
    fields/
    recommendation/
    timeline/
    agronomy/
    telemetry/
```

### Step 6. AI agent orchestration flow

The Flutter-side AI agent should use APIs in this order for a normal farmer session:

1. Firebase sign-in.
2. `POST /users/sync`.
3. `GET /users/me`.
4. `GET /dashboard/visibility`.
5. `GET /fields/` and `GET /fields/summary`.
6. `GET /agronomy/weather` and `GET /agronomy/mandi-prices`.
7. For a selected field, call `POST /recommend/calculate` on port `8002`.
8. If the farmer accepts a crop, call `POST /recommend/select`.
9. Create or fetch crop timeline through port `8001`.
10. Use `/chatbot/message`, `/chatbot/voice`, and `/disease/predict` as user-triggered AI tools.

The agent should never call MongoDB, Redis, or the ML service directly from Flutter.

## 5. API Catalog By Module

### 5.1 Health And Root

Base: main backend `http://localhost:8000`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/` | No | Returns welcome message and backend version |
| `GET` | `/health` | No | Returns `{"status":"healthy"}` |

Timeline service:

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | No | Timeline health check |

Recommendation engine:

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/` | No | Service metadata and route hints |
| `GET` | `/health` | No | Recommendation engine health check |

ML service:

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/` | No | Service metadata |
| `GET` | `/health` | No | ML model count and service health |
| `GET` | `/models` | No | Supported disease models |
| `POST` | `/predict` | No internal auth | Internal multipart disease inference |

### 5.2 Users

Base: main backend `/api/v1/users`

All endpoints require `Authorization: Bearer <Firebase ID token>`.

| Method | Path | Body or query | Response | Purpose |
|---|---|---|---|---|
| `POST` | `/sync` | None | `{ "message": "User synchronized successfully" }` | Upsert MongoDB user after Firebase login |
| `GET` | `/me` | None | User document or `{id,message}` | Fetch profile |
| `POST` | `/me` | `FarmerProfile` JSON | `{message, updated_at}` | Update profile |
| `POST` | `/logout` | None | `{message}` | Revoke Firebase refresh tokens |
| `POST` | `/deactivate` | None | `{message}` | Soft deactivate account |
| `DELETE` | `/me` | None | `{message}` | Hard delete account |
| `GET` | `/activities?limit=20&offset=0` | Query | `{activities:[...]}` | Activity history |

`FarmerProfile` request:

```json
{
  "display_name": "Asha Patil",
  "preferred_language": "hi",
  "location": {
    "latitude": 19.076,
    "longitude": 72.8777
  },
  "farm_size_acres": 4.5,
  "avatar_url": "https://example.com/avatar.png",
  "phone_number": "+919999999999"
}
```

Flutter example:

```dart
final dio = getIt<Dio>(instanceName: 'authApi');

Future<void> syncUser() async {
  await dio.post('/users/sync');
}

Future<Map<String, dynamic>> getProfile() async {
  final response = await dio.get('/users/me');
  return Map<String, dynamic>.from(response.data);
}
```

### 5.3 Admin Auth

Base: main backend `/api/v1/admin/auth`

Requires Firebase admin or super_admin custom claims.

| Method | Path | Required claims | Response | Purpose |
|---|---|---|---|---|
| `GET` | `/me` | admin role | `AdminAuthResponse` | Read admin session |
| `POST` | `/sync` | admin role | `{message, admin}` | Sync admin profile |
| `POST` | `/logout` | admin role | `{message}` | Revoke admin refresh tokens |

`AdminAuthResponse` shape:

```json
{
  "uid": "firebase-uid",
  "email": "admin@fasalx.com",
  "display_name": "FasalX Admin",
  "is_active": true,
  "access": {
    "role": "admin",
    "permissions": ["dashboard:manage"]
  }
}
```

### 5.4 Dashboard Visibility

Base: main backend `/api/v1`

| Method | Path | Auth | Body | Purpose |
|---|---|---|---|---|
| `GET` | `/dashboard/visibility` | No | None | Public dashboard component flags |
| `GET` | `/admin/dashboard/visibility` | `dashboard:manage` | None | Admin read |
| `PUT` | `/admin/dashboard/visibility` | `dashboard:manage` | `DashboardVisibilityUpdate` | Replace component config |
| `PATCH` | `/admin/dashboard/visibility/toggle` | `dashboard:manage` | `{component, visible}` | Toggle one component |

Response:

```json
{
  "scope": "global",
  "components": {
    "weather": true,
    "mandi_prices": true,
    "iot_data": true,
    "expense_ledger": true,
    "timeline": true,
    "recommendation": true,
    "chatbot_button": true
  },
  "updated_at": null,
  "updated_by": null
}
```

Frontend usage:

```dart
final response = await dio.get('/dashboard/visibility');
final components = response.data['components'] as Map<String, dynamic>;
final showChatbot = components['chatbot_button'] == true;
```

### 5.5 System Config

Base: main backend `/api/v1/admin/system/config`

Requires `system:manage`, normally super_admin.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/admin/system/config` | `system:manage` | Read global recommendation and MSP config |
| `PUT` | `/admin/system/config` | `system:manage` | Update global config |

Important field: `recommendation.suitability_weights` must total `1.0`; backend validates this.

### 5.6 Chatbot

Base: main backend `/api/v1/chatbot`

Requires Firebase user token. This is the primary conversational AI surface for the Flutter app.

| Method | Path | Content type | Body | Response |
|---|---|---|---|---|
| `POST` | `/message` | `application/json` | `{ "message": "..." }` | `{reply, model, audio?}` |
| `POST` | `/voice` | `multipart/form-data` | `audio=<file>` | `{transcript, reply, model, audio?}` |

Text request:

```json
{
  "message": "My tomato leaves have yellow spots. What should I do?"
}
```

Text response:

```json
{
  "reply": "The symptoms may indicate early blight...",
  "model": "gemini-2.5-flash",
  "audio": {
    "data": "base64-audio",
    "mime_type": "audio/wav",
    "encoding": "base64"
  }
}
```

Allowed voice content types include `audio/wav`, `audio/mpeg`, `audio/mp3`, `audio/mp4`, `audio/webm`, `audio/ogg`, `audio/aac`, and `audio/flac`. Max upload size is configured as `CHATBOT_AUDIO_MAX_UPLOAD_BYTES`, default `10 MB`.

Flutter text example:

```dart
Future<String> sendChatMessage(String message) async {
  final response = await dio.post('/chatbot/message', data: {'message': message});
  return response.data['reply'] as String;
}
```

Flutter voice example:

```dart
Future<Map<String, dynamic>> sendVoice(String filePath) async {
  final form = FormData.fromMap({
    'audio': await MultipartFile.fromFile(filePath, filename: 'question.webm'),
  });
  final response = await dio.post('/chatbot/voice', data: form);
  return Map<String, dynamic>.from(response.data);
}
```

### 5.7 Disease Detection

Base: main backend `/api/v1/disease`

Requires Firebase user token. Prefer this endpoint over calling ML service directly because it falls back to Gemini advisory when the crop is unsupported or when only text is supplied.

| Method | Path | Content type | Fields | Purpose |
|---|---|---|---|---|
| `POST` | `/predict` | `multipart/form-data` | `crop_name`, optional `image`, optional `issue_text` or `text_issue` | Predict disease from image or text |

Behavior:

| Input | Backend behavior |
|---|---|
| Supported crop plus image | Calls ML service and returns ML result |
| Unsupported crop | Uses Gemini disease advisory |
| No image but text issue supplied | Uses Gemini advisory |
| No image and no text | `400` error |
| Invalid image type | `415` error |
| Image over max size | `413` error |

Allowed image types: `image/jpeg`, `image/png`, `image/webp`. Default max size: `8 MB`.

Response shape:

```json
{
  "success": true,
  "disease": "Early Blight",
  "confidence": 94.2,
  "top3": [
    {"disease": "Early Blight", "confidence": 94.2}
  ],
  "error": null,
  "source": "ml",
  "model_supported": true
}
```

Flutter example:

```dart
Future<Map<String, dynamic>> predictDisease({
  required String cropName,
  String? imagePath,
  String? issueText,
}) async {
  final form = FormData.fromMap({
    'crop_name': cropName,
    if (issueText != null) 'issue_text': issueText,
    if (imagePath != null)
      'image': await MultipartFile.fromFile(imagePath, filename: 'leaf.jpg'),
  });

  final response = await dio.post('/disease/predict', data: form);
  return Map<String, dynamic>.from(response.data);
}
```

Hidden compatibility alias:

```text
POST /api/v1/agronomy/disease/predict
```

This alias exists in code with `include_in_schema=False`; new Flutter code should use `/disease/predict`.

Duplicate service route:

```text
POST http://localhost:8002/api/v1/disease/predict
```

The recommendation engine app also includes the same disease router. Prefer the main backend path on port `8000` unless the app is intentionally talking to the recommendation service.

### 5.8 Agronomy

Base: main backend `/api/v1/agronomy`

Requires Firebase user token.

| Method | Path | Query/body | Response | Purpose |
|---|---|---|---|---|
| `GET` | `/weather?lat=&lon=` | Optional `lat`, `lon` | `WeatherResponse` | Hyper-local weather; location fallback if GPS absent |
| `GET` | `/mandi` | Optional `state`, `market`, `commodity` | Market data | Commodity prices |
| `GET` | `/mandi-prices` | Same as `/mandi` | Market data | Alias for commodity prices |
| `POST` | `/templates` | `CropTemplate` JSON | `{message,id,updated_at}` | Create crop template |
| `GET` | `/templates` | None | `list[dict]` | List crop templates |

Weather response:

```json
{
  "temperature": 28.4,
  "humidity": 72.0,
  "precipitation": 1.2,
  "description": "Partly cloudy (Location Source: gps)"
}
```

Crop template request:

```json
{
  "crop_name": "Wheat",
  "variety": "HD-2967",
  "total_duration_days": 120,
  "stages": [
    {
      "name": "Sowing",
      "duration_days": 7,
      "instructions": "Maintain seed depth and first irrigation."
    }
  ]
}
```

Location fallback logic:

1. Use explicit `lat/lon`, `state`, or `market` query when supplied.
2. Fall back to the user profile location where possible.
3. Fall back to IP-derived location.

Flutter weather example:

```dart
final response = await dio.get(
  '/agronomy/weather',
  queryParameters: {'lat': 19.076, 'lon': 72.8777},
);
```

### 5.9 Geo

Base: main backend `/api/v1/geo`

Current implementation is public.

| Method | Path | Body | Response | Purpose |
|---|---|---|---|---|
| `POST` | `/` | `{lat, lon}` | `GeoResponse` | Reverse geocode coordinates to administrative data |

Request:

```json
{
  "lat": 19.076,
  "lon": 72.8777
}
```

Response:

```json
{
  "status": "success",
  "message": null,
  "coordinates": {"lat": 19.076, "lon": 72.8777},
  "address": {
    "state": "Maharashtra",
    "district": "Mumbai",
    "block": null,
    "pincode": "400001"
  },
  "codes": {
    "state_lgd": 27,
    "district_lgd": 519
  }
}
```

Use this to enrich profile creation and field registration UI after GPS permission is granted.

### 5.10 Fields

Base: main backend `/api/v1/fields`

Requires Firebase user token.

| Method | Path | Body | Response | Purpose |
|---|---|---|---|---|
| `POST` | `/` | `FieldRegistrationRequest` | `{status, field_id}` | Register a field |
| `GET` | `/` | None | `FieldResponse[]` | List user's fields |
| `GET` | `/summary` | None | `FarmOverviewResponse` | Aggregated farm overview |

Register field request:

```json
{
  "name": "North Plot",
  "lat": 19.076,
  "lon": 72.8777,
  "area": 2.5
}
```

Field response:

```json
{
  "id": "field-id",
  "name": "North Plot",
  "lat": 19.076,
  "lon": 72.8777,
  "area": 2.5,
  "selected_crop": "Tomato"
}
```

Farm overview:

```json
{
  "total_fields": 2,
  "total_area_acres": 6.0,
  "estimated_gross_revenue": 120000.0,
  "estimated_total_cost": 42000.0,
  "estimated_net_profit": 78000.0,
  "active_crops": ["Tomato", "Wheat"]
}
```

Recommendation depends on field IDs, so the agent should register/list fields before calling `/recommend/calculate`.

### 5.11 Telemetry

Base: main backend `/api/v1/telemetry`

Requires Firebase user token.

| Method | Path | Body | Response | Purpose |
|---|---|---|---|---|
| `POST` | `/data` | `IoTDevicePayload` | `{message,id}` | Ingest soil sensor telemetry |

Request:

```json
{
  "device_id": "soil-node-001",
  "moisture": 42.5,
  "temperature": 26.2,
  "ph": 6.8,
  "nitrogen": 120.0,
  "phosphorus": 35.0,
  "potassium": 80.0,
  "timestamp": "2026-05-12T09:00:00Z"
}
```

If `timestamp` is absent, the backend assigns server time. The backend also attaches `user_id` and `sync_status`.

### 5.12 Recommendation Engine

Base: recommendation service `/api/v1/recommend` on port `8002`.

Requires Firebase user token.

| Method | Path | Body | Response | Purpose |
|---|---|---|---|---|
| `POST` | `/calculate` | `{field_id,target_season?}` | `DualRecommendationResponse` | Generate seasonal and horticulture recommendations |
| `POST` | `/select` | `{field_id,recommendation_id,crop_name}` | `{status,message}` | Mark accepted crop for history-aware future recommendations |

Calculate request:

```json
{
  "field_id": "field-id-from-fields-api",
  "target_season": "Kharif"
}
```

Response:

```json
{
  "seasonal": [
    {
      "id": "recommendation-session-id",
      "crop_name": "Maize",
      "type": "seasonal",
      "gestation_period": null,
      "investment_lifespan": null,
      "final_score": 0.86,
      "category": "Highly Recommended",
      "why_this_crop": "Strong soil and rainfall match...",
      "breakdown": {
        "suitability_score": 0.88,
        "profitability_score": 0.82
      },
      "hex_color": "#4CAF50",
      "icon_slug": "maize",
      "action_priority": 1,
      "action_plan": [
        {"task": "Prepare seed bed", "month": "June"}
      ]
    }
  ],
  "horticulture": []
}
```

Select request:

```json
{
  "field_id": "field-id-from-fields-api",
  "recommendation_id": "recommendation-session-id",
  "crop_name": "Maize"
}
```

Agent flow:

1. Ensure a field exists through `/api/v1/fields`.
2. Call `POST http://localhost:8002/api/v1/recommend/calculate`.
3. Display both `seasonal` and `horticulture` tabs.
4. When user chooses a crop, call `/recommend/select`.
5. Refresh `GET /api/v1/fields/` so `selected_crop` appears in the UI.

### 5.13 Field Intelligence

Base: recommendation service `/api/v1/ingest` on port `8002`.

Current implementation is public.

| Method | Path | Query | Response | Purpose |
|---|---|---|---|---|
| `GET` | `/?lat=&lon=&commodity=` | Required `lat`, `lon`; optional `commodity` | `FieldIntelligence` | Weather, soil, market bundle for a coordinate |

Response:

```json
{
  "coordinates": {"lat": 19.076, "lon": 72.8777},
  "weather": {
    "temperature_min": 22.0,
    "temperature_max": 31.0,
    "humidity": 70.0,
    "rainfall_current": 1.2,
    "rainfall_history_12m": 850.0,
    "gdd": 16.5,
    "description": "Partly cloudy"
  },
  "soil": {
    "N": 120.0,
    "P": 35.0,
    "K": 80.0,
    "S": 10.0,
    "Zn": 0.7,
    "Fe": 4.2,
    "Cu": 0.3,
    "Mn": 2.1,
    "B": 0.4,
    "pH": 6.8,
    "EC": 0.3,
    "OC": 0.6,
    "source": "district_average"
  },
  "market": {
    "state": "Maharashtra",
    "market": "Mumbai",
    "commodities": [
      {
        "commodity": "Tomato",
        "modal_price": 2200.0,
        "msp": null,
        "profitability_index": null,
        "source": "data_gov"
      }
    ],
    "source": "data_gov"
  },
  "errors": {}
}
```

Use this for advanced diagnostics screens. Normal recommendation cards can rely on `/recommend/calculate` instead.

### 5.14 Timeline Service

Base: timeline service `/api/v1/timeline` on port `8001`.

Auth is currently bypassed in route code for frontend development. The model still carries `user_metadata.user_id`, so pass the Firebase UID explicitly.

| Method | Path | Body/query | Response | Purpose |
|---|---|---|---|---|
| `POST` | `/` | `UserCropTimeline` | `UserCropTimeline` | Create a crop timeline |
| `GET` | `/{user_id}` | Path user ID | `UserCropTimeline` | Get user's timeline |
| `POST` | `/sync-iot` | Query params | `{message}` | Update environmental snapshot and queue recalculation |
| `PATCH` | `/recalibrate` | Query params | `{message}` | Manually mark milestone complete |

Create timeline request:

```json
{
  "user_metadata": {
    "user_id": "firebase-uid",
    "crop_id": "tomato",
    "sowing_date": "2026-05-01T00:00:00Z",
    "location": {
      "type": "Point",
      "coordinates": [72.8777, 19.076]
    },
    "t_base": 10.0
  },
  "lifecycle_state": {
    "current_stage": "Sowing",
    "progress_percentage": 0.0,
    "total_gdd": 0.0
  },
  "milestone_map": [
    {
      "name": "Germination",
      "type": "micro",
      "status": "predicted",
      "target_gdd": 80.0,
      "trigger_logic": "total_gdd >= 80",
      "predicted_date": null,
      "completed_date": null,
      "confidence_score": 1.0
    }
  ],
  "environmental_snapshot": {
    "last_updated": "2026-05-12T09:00:00Z",
    "t_max": 32.0,
    "t_min": 22.0,
    "soil_moisture": 45.0,
    "source": "api",
    "weight": 0.8
  }
}
```

Important GeoJSON coordinate order is `[longitude, latitude]`, not `[latitude, longitude]`.

Sync IoT query example:

```text
POST /api/v1/timeline/sync-iot?user_id=firebase-uid&t_max=33&t_min=22&soil_moisture=44
```

Manual recalibrate query example:

```text
PATCH /api/v1/timeline/recalibrate?user_id=firebase-uid&milestone_name=Germination
```

Flutter timeline example:

```dart
final timelineApi = getIt<Dio>(instanceName: 'timelineApi');

Future<Map<String, dynamic>> getTimeline(String uid) async {
  final response = await timelineApi.get('/timeline/$uid');
  return Map<String, dynamic>.from(response.data);
}
```

### 5.15 Internal ML Service

Base: ML service root, usually Docker internal `http://ml-service:8003`.

Flutter should not call this service directly in production. It is listed for completeness.

| Method | Path | Body | Response | Purpose |
|---|---|---|---|---|
| `GET` | `/health` | None | `HealthResponse` | Service status and model count |
| `GET` | `/models` | None | `{success,models,error}` | Supported crop models |
| `POST` | `/predict` | multipart `crop_name`, `image` | `PredictionResponse` | Disease inference |

Direct ML request:

```text
Content-Type: multipart/form-data
crop_name=tomato
image=@leaf.jpg
```

Direct ML response:

```json
{
  "success": true,
  "disease": "Tomato Early Blight",
  "confidence": 94.2,
  "top3": [
    {"disease": "Tomato Early Blight", "confidence": 94.2}
  ],
  "error": null
}
```

## 6. Frontend Agent Implementation Checklist

Use this checklist for the AI agent building the Flutter integration.

1. Add Firebase initialization if missing.
2. Add `ApiBases` for auth, timeline, and recommendation service URLs.
3. Replace the single default Dio client with three named clients.
4. Add Firebase bearer token interceptor.
5. Add shared `ApiFailure` mapper.
6. Implement repositories:
   - `AuthRepository`: `/users/sync`, `/users/me`, profile update, logout.
   - `DashboardRepository`: `/dashboard/visibility`.
   - `AgronomyRepository`: weather, mandi, templates.
   - `FieldRepository`: create/list/summary.
   - `RecommendationRepository`: calculate/select on port `8002`.
   - `TimelineRepository`: create/get/sync/recalibrate on port `8001`.
   - `ChatbotRepository`: text and voice message.
   - `DiseaseRepository`: multipart disease prediction.
   - `TelemetryRepository`: sensor ingestion.
7. Wire repositories into Riverpod providers.
8. Add loading/error states around each API call.
9. Add image/audio upload progress for disease and chatbot voice.
10. Add token-expired handling: sign out or force Firebase reauth on `TOKEN_EXPIRED` or `TOKEN_REVOKED`.
11. Add environment launch commands for web, emulator, and physical device.

## 7. Suggested Repository Method Signatures

```dart
abstract class ChatbotRepository {
  Future<ChatbotReply> sendMessage(String message);
  Future<ChatbotVoiceReply> sendVoice(String audioPath);
}

abstract class DiseaseRepository {
  Future<DiseasePrediction> predict({
    required String cropName,
    String? imagePath,
    String? issueText,
  });
}

abstract class RecommendationRepository {
  Future<DualRecommendation> calculate({
    required String fieldId,
    String? targetSeason,
  });

  Future<void> select({
    required String fieldId,
    required String recommendationId,
    required String cropName,
  });
}

abstract class TimelineRepository {
  Future<UserCropTimeline> create(UserCropTimeline request);
  Future<UserCropTimeline> getByUser(String userId);
  Future<void> syncIot({
    required String userId,
    required double tMax,
    required double tMin,
    required double soilMoisture,
  });
  Future<void> recalibrate({
    required String userId,
    required String milestoneName,
  });
}
```

## 8. Launch Commands

Flutter web, main backend on localhost:

```powershell
cd frontend_client
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000/api/v1 --dart-define=TIMELINE_API_BASE_URL=http://localhost:8001/api/v1 --dart-define=RECOMMENDATION_API_BASE_URL=http://localhost:8002/api/v1
```

Android emulator:

```powershell
flutter run -d emulator-5554 --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1 --dart-define=TIMELINE_API_BASE_URL=http://10.0.2.2:8001/api/v1 --dart-define=RECOMMENDATION_API_BASE_URL=http://10.0.2.2:8002/api/v1
```

Physical phone on same Wi-Fi:

```powershell
flutter run --dart-define=API_BASE_URL=http://192.168.1.50:8000/api/v1 --dart-define=TIMELINE_API_BASE_URL=http://192.168.1.50:8001/api/v1 --dart-define=RECOMMENDATION_API_BASE_URL=http://192.168.1.50:8002/api/v1
```

Replace `192.168.1.50` with the development machine's LAN IP.

## 9. Common Integration Pitfalls

| Pitfall | Fix |
|---|---|
| Calling `localhost` from Android emulator | Use `10.0.2.2` |
| Calling recommendation endpoints on port `8000` | Use port `8002` for `/api/v1/recommend/*` and `/api/v1/ingest/` |
| Calling timeline endpoints on port `8000` | Use port `8001` |
| Sending JSON to disease or voice endpoints | Use `multipart/form-data` |
| Missing bearer token | Add Firebase ID token interceptor |
| Expired/revoked token | Refresh ID token or sign user out |
| GeoJSON coordinates reversed | Timeline location uses `[lon, lat]` |
| Treating timeline auth as production-ready | Current route code has auth bypass comments; harden before release |
| Admin UI using farmer token | Admin endpoints require Firebase custom claims |
| Assuming templates are admin-protected | Current `/agronomy/templates` uses normal user auth only |

## 10. Minimal Smoke Test Plan

Run these in order after wiring Flutter:

1. Sign in with Firebase and call `POST /users/sync`.
2. Call `GET /users/me`; verify UID matches Firebase user.
3. Call `GET /dashboard/visibility`; verify dashboard toggles render.
4. Create a field with `POST /fields/`.
5. List fields with `GET /fields/`.
6. Call `GET /agronomy/weather?lat=...&lon=...`.
7. Call recommendation `POST http://localhost:8002/api/v1/recommend/calculate`.
8. Send a chatbot text message.
9. Upload a disease image or text issue.
10. Create and fetch a timeline on `http://localhost:8001`.

## 11. What To Harden Before Production

1. Put timeline endpoints behind `verify_token` and remove development bypass.
2. Decide whether `/api/v1/geo/` and `/api/v1/ingest/` should remain public.
3. Restrict CORS from `allow_origins=["*"]` to the deployed Flutter web domains.
4. Consider routing timeline and recommendation behind one public API gateway.
5. Add request/response DTOs in Flutter and tests for every repository.
6. Add retry/backoff only for idempotent reads, not for mutation endpoints like crop selection.
7. Store only non-sensitive cached response data in `SharedPreferences`; do not store Firebase ID tokens manually.
