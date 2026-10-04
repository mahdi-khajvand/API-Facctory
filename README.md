⚡ API Factory Pro
Build. Secure. Monitor. Control.

یک پنل مدیریتی سبک، مدرن و یکپارچه برای ساخت، مدیریت، مانیتورینگ و کنترل وب سرویس ها است؛ با این هدف که فاصله بین دیتابیس، سرویس‌های Python و یک API قابل استفاده را تا حد ممکن کوتاه کند.

به‌جای اینکه برای هر API به‌صورت جداگانه کدنویسی، تنظیم پورت، اجرای Process، بررسی Log، مدیریت API Key و پایش سرویس انجام شود، API Factory همه این مراحل را در یک Service Control Plane متمرکز می‌کند.

From Database to API — From API to Monitoring.

✨ چرا API Factory Pro؟

در بسیاری از محیط‌های سازمانی، ساخت یک Web Service ساده می‌تواند شامل چندین مرحله مستقل باشد:

Database
   ↓
Write Python Code
   ↓
Configure API
   ↓
Choose Port
   ↓
Run Process
   ↓
Monitor Service
   ↓
Read Logs
   ↓
Detect Errors
   ↓
Manage Access
   ↓
Notify Administrator




🚀 قابلیت‌های اصلی :

🗄️ اتصال به MySQL و PostgreSQL
⚡ ساخت Web Service از طریق Wizard
🧩 پشتیبانی از Join چند جدول
🐍 ساخت API با کدنویسی Python/Flask
▶️ اجرای سرویس‌ها با PM2
⏹️ Start / Stop / Delete سرویس‌ها
🔌 مدیریت Portها
🔑 مدیریت API Key
🛠️ ویرایش مستقیم Source Code سرویس‌ها
📋 مشاهده Log سرویس‌ها
🚨 تشخیص HTTP 5xx و ایجاد Alarm
📊 مشاهده Traffic و Latency
👤 مدیریت کاربران و Permissionها
💬 اتصال به Bale Bot
🔔 ارسال Notification و Alarm از طریق بله
🔄 Polling و Webhook برای Bale
🎨 رابط کاربری مدرن RTL
🔐 Authentication و Session Management
📱 رابط Responsive برای اندازه‌های مختلف صفحه
🖥️ Dashboard
داشبورد، نقطه شروع سیستم است.

در این بخش وضعیت کلی محیط API Factory در یک نگاه قابل مشاهده است.

اطلاعاتی مانند:

تعداد سرویس‌ها
وضعیت سرویس‌ها
وضعیت Runtime
سرویس‌های اخیر
وضعیت کلی زیرساخت


🗄️ Database
![database](docs/screenshots/database.png)

بخش Database محل تعریف و مدیریت Connectionهای دیتابیس است.

API Factory در حال حاضر از:

MySQL
PostgreSQL

پشتیبانی می‌کند.

پس از ذخیره، Connection برای استفاده در API Builder در دسترس قرار می‌گیرد.

⚡ Create API

یکی از مهم‌ترین بخش‌های API Factory.

این بخش دو روش اصلی برای ساخت سرویس در اختیار کاربر قرار می‌دهد:

1. 🧙 Wizard
![wizard](docs/screenshots/wizard.png)


برای کاربرانی که می‌خواهند بدون نوشتن کامل Backend، یک API مبتنی بر Database ایجاد کنند.

** می‌توان از چند جدول دیتابیس یک API ساخت:

Customers
     │
     ├──── JOIN ──── MeterInfo
     │
     └──── JOIN ──── Billing

و خروجی را به شکل یک Endpoint در اختیار سایر سیستم‌ها قرار داد.


2. 👨‍💻 کد نویسی
![code](docs/screenshots/code.png)


برای Developerهایی که کنترل کامل روی API را می‌خواهند.

در این حالت کاربر مستقیماً کد Python/Flask سرویس را وارد می‌کند.

این حالت برای APIهای پیچیده‌تر، Logicهای اختصاصی، محاسبات سفارشی و Integrationهای خاص مناسب است.

🔑 API Keys
![keys](docs/screenshots/keys.png)


بخش API Keys برای کنترل دسترسی سرویس‌ها طراحی شده است.

برای هر Service می‌توان یک یا چند API Key تعریف کرد.

این ساختار اجازه می‌دهد مصرف‌کنندگان مختلف یک API با Credentialهای جداگانه کار کنند.

🔌 Ports

هر Service برای اجرا به یک Port نیاز دارد.

بخش Ports محیطی متمرکز برای مشاهده و مدیریت Portهای مرتبط با APIها فراهم می‌کند.

در این قسمت می‌توان وضعیت Portها را مشاهده کرد:

Port
Status
PID
Process
Service

همچنین محدوده Portهای آزاد API نیز نمایش داده می‌شود.

این موضوع در محیط‌هایی که تعداد زیادی API داخلی روی یک Server اجرا می‌شوند اهمیت زیادی دارد.

🛠️ API Management
![manage](docs/screenshots/manage.png)


این بخش مرکز مدیریت Web Serviceهای ساخته‌شده است.

همچنین عملیات مدیریتی اصلی در اختیار Administrator قرار دارد:
Delete
Edit
View Code
API Editor

یکی از قابلیت‌های کاربردی این بخش، ویرایش مستقیم Source Code سرویس است.

Administrator می‌تواند:

Select Service
      ↓
Load Python Code
      ↓
Edit
      ↓
Save Changes

را مستقیماً از داخل پنل انجام دهد.

⚙️ Services

بخش Services نمای Runtime سرویس‌هاست.

این قسمت با PM2 ارتباط دارد و امکان کنترل Lifecycle سرویس‌ها را فراهم می‌کند.

عملیات اصلی:

▶️ Start
⏹️ Stop
🗑️ Delete
📄 مشاهده Code
📋 مشاهده Logs

به این ترتیب Administrator برای عملیات روزمره الزاماً نیازی به ورود مستقیم به Shell Server ندارد.

📋 Service Logs

Debug کردن یک API بدون Log تقریباً غیرممکن است.

API Factory امکان مشاهده Log سرویس‌ها را از داخل پنل فراهم می‌کند.

به‌جای:

pm2 logs service_name

Administrator می‌تواند Log را مستقیماً از UI مشاهده کند.

🚨 Alarms

API Factory می‌تواند HTTP Server Errorهای واقعی را شناسایی کند.

تمرکز این بخش روی خطاهای:

HTTP 5xx

است.

این بخش یک لایه ساده اما کاربردی برای تشخیص سریع سرویس‌های مشکل‌دار ایجاد می‌کند.

📊 Traffic

بخش Traffic برای مشاهده رفتار سرویس‌ها طراحی شده است.

اطلاعاتی مانند:

Request Count
Endpoint
HTTP Status
Response Time
Response Size
Timestamp

قابل بررسی هستند.

این اطلاعات کمک می‌کنند Administrator متوجه شود:

کدام API بیشتر استفاده می‌شود؟

کدام سرویس Latency بیشتری دارد؟

چه Endpointهایی بیشتر خطا می‌دهند؟

چه زمانی ترافیک افزایش پیدا کرده است؟

👤 Users

API Factory فقط برای یک Administrator ساخته نشده است.

بخش Users امکان تعریف کاربران مختلف را فراهم می‌کند.

برای هر User می‌توان مواردی مانند:

Username
Password
Role
Permissions

را مشخص کرد.

💬 Bale Bot
![bale](docs/screenshots/bale.png)


یکی از قابلیت‌های متفاوت API Factory، اتصال آن به پیام‌رسان بله است.

هدف این بخش این است که Administrator فقط به Dashboard وابسته نباشد و بتواند بخشی از وضعیت سیستم را از طریق Messenger دریافت یا کنترل کند.

امکانات Bale Bot
🔐 Bot Configuration

امکان تعریف:

Bot Token
Default Chat ID
Enable / Disable
Alarm Notifications
Service Down Notifications
Polling

وجود دارد.

🎯 چه کسانی از API Factory Pro سود می‌برند؟

API Factory برای هر پروژه‌ای ساخته نشده است؛ بیشترین ارزش آن در محیط‌هایی است که تعداد قابل توجهی سرویس داخلی وجود دارد.

🏢 سازمان‌ها و شرکت‌ها

برای سازمان‌هایی که چندین سیستم داخلی دارند و نیاز دارند:

Database → API → Monitoring

را در یک محیط متمرکز مدیریت کنند.

🧑‍💻 Data Engineerها

برای Data Engineerهایی که مرتباً باید از دیتابیس‌های سازمانی API بسازند.

به‌خصوص زمانی که:

Data Source مشخص است
Queryها نسبتاً استاندارد هستند
تعداد APIها زیاد است
Deployment دستی زمان‌بر شده است

🧠 Data Scientistها

برای Data Scientistهایی که نیاز دارند خروجی مدل یا Dataset خود را به‌صورت API در اختیار سایر سیستم‌ها قرار دهند.

به‌جای اینکه هر بار یک Backend کامل ساخته شود:

Model / Query
     ↓
API Factory
     ↓
REST API



پیشنهاد می‌شود محیط اجرا حداقل شامل موارد زیر باشد:

Python 3.10+
PM2
MySQL and/or PostgreSQL
Linux Server
Install
git clone <YOUR_REPOSITORY_URL>
cd api_factory

سپس:

pip install -r requirements.txt
Run
uvicorn app:app --host 0.0.0.0 --port 8501

سپس پنل از طریق:

http://SERVER_IP:8501

در دسترس خواهد بود.

