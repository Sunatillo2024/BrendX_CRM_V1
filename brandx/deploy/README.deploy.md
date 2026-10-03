# BrandX — Production'ga Docker bilan deploy qilish qo'llanmasi

Bu qo'llanma **Ubuntu serverda allaqachon ishlab turgan Telegram bot bilan
to'qnashmasdan** BrandX (Django) ilovasini production'ga chiqarishni
qadam-baqadam tushuntiradi.

---

## 0. Domensiz, IP orqali deploy (joriy stsenariy: 129.101.125.203)

Domen yo'q, sayt `http://129.101.125.203` da ochiladi. Buning uchun:

1. `deploy/.env.prod` **tayyor** (git-ignored - serverga `scp` qiling):
   - `ALLOWED_HOSTS=129.101.125.203,localhost,127.0.0.1`
     (`localhost,127.0.0.1` MAJBURIY - konteyner healthcheck shu hostga uriladi)
   - `CSRF_TRUSTED_ORIGINS=http://129.101.125.203`
   - `BRANDX_HTTP_BIND=0.0.0.0` + `BRANDX_HTTP_PORT=80` → to'g'ridan-to'g'ri ochiq
   - HTTPS yoqilmagan (`SECURE_*` False) - domensiz Let's Encrypt bo'lmaydi
2. Serverda firewall:
   ```bash
   sudo ufw allow OpenSSH
   sudo ufw allow 80/tcp
   sudo ufw enable
   ```
3. 80-port band bo'lsa (masalan nginx bilan bot webhook): `.env.prod` da
   `BRANDX_HTTP_PORT=8080` qiling va `CSRF_TRUSTED_ORIGINS=http://129.101.125.203:8080`
   yozing → sayt `http://129.101.125.203:8080` da ochiladi.
4. Kodni serverga ko'chirish (repo private bo'lsa ham ishlaydi):
   ```bash
   rsync -av --exclude '.env' --exclude '__pycache__' --exclude 'backend/media' \
     ./ user@129.101.125.203:~/brandx/
   scp deploy/.env.prod user@129.101.125.203:~/brandx/deploy/.env.prod
   ```
5. Birinchi ishga tushirish: `./deploy/scripts/deploy.sh --skip-tests`
   (`.env.prod` da `BOOTSTRAP_ADMIN=true` bo'lsa platform admin avtomatik yaratiladi).
   Admin: `http://129.101.125.203/admin/` yoki `http://129.101.125.203/platform/login/`.
   Do'kon va egani **Platform → Do'konlar → yaratish → egasini boshqarish**
   orqali qo'shing. Keyin `.env.prod` da `BOOTSTRAP_ADMIN=false` qiling.

> **HTTP ogohlantirishi:** parollar/PIN'lar shifrsiz ketadi. Imkon qadar tez orada
> domen ulab HTTPS'ga o'ting (9-bo'lim) yoki kamida `ufw` bilan kirimni cheklang.

---

## 1. Arxitektura va port strategiyasi (eng muhim qism)

Ikki xizmat bir serverda yashaydi: **Telegram bot** (mavjud) va **BrandX** (yangi).
Ular bir-biriga xalaqit bermasligi uchun:

| Resurs | Telegram bot | BrandX (bu setup) → to'qnashuv yo'q |
|--------|--------------|-------------------------------------|
| Docker tarmoq | (o'ziniki) | **`brandx_prod_network`** — alohida bridge tarmoq |
| PostgreSQL | (bo'lsa o'ziniki) | Hostga **port ochilmaydi**, faqat `brandx_prod_network` ichida |
| Django/Gunicorn | — | Hostga **port ochilmaydi**, faqat web konteyner orqali |
| Public HTTP | (bot webhook bo'lsa, o'ziniki) | Faqat **bitta** port: `127.0.0.1:8080` (loopback) |
| Volume'lar | (o'ziniki) | `brandx_postgres_data`, `brandx_media_data` |
| Docker project | (o'ziniki) | **`brandx-prod`** — alohida namespace (dev stack'dan ham ajratilgan) |

**Nima uchun xavfsiz:**

- **PostgreSQL** hostda umuman port ochmaydi — unga faqat Docker ichidagi
  `backend` konteyneri yeta oladi. Demak u bot bilan hech qachon to'qnashmaydi.
- **Yagona ochiq port** — `backend` (Django/Gunicorn) konteyneri. U
  **loopback** (`127.0.0.1`) ga bog'lanadi, ya'ni faqat serverning o'zi ko'ra
  oladi. Bu port (default `8080`) bo'sh bo'lishi kerak.
- Agar Telegram bot **long polling** ishlatsa — u umuman keluvchi port ochmaydi
  (faqat chiquvchi HTTPS), shuning uchun to'qnashuv umuman bo'lmaydi.
- Agar bot **webhook** ishlatsa — u odatda `80/443` yoki o'z portini egallaydi.
  BrandX `80/443` ga tegilmaydi, chunki u host nginx orqasida `127.0.0.1:8080`
  da turadi.

```
                Internet
                   │
        ┌──────────┴───────────┐
        │  Host Nginx (80/443) │   ← bot webhook ham, BrandX ham shu yerga server blok
        └──────────┬───────────┘
                   │ proxy_pass http://127.0.0.1:8080
        ┌──────────┴─────────────────────────────┐
        │  Docker: brandx_prod_network                 │
        │                                         │
        │   backend (gunicorn:8000) ──► postgres:5432
        │   hostda ochilgan: 127.0.0.1:8080       │        (hostda port YO'Q)
        └─────────────────────────────────────────┘
```

---

## 2. Fayl tuzilishi

```
deploy/
├── docker-compose.prod.yml     # production stack
├── docker-compose.test.yml     # izolyatsiyalangan test stack
├── .env.prod.example           # env namunasi → .env.prod nusxa olinadi
├── proxy/brandx.conf           # host nginx server blok (bot yonida)
├── scripts/
│   ├── preflight.sh            # port/tooling tekshiruvi
│   ├── test.sh                 # Docker ichida testlar
│   ├── backup.sh               # DB + media backup
│   ├── deploy.sh              # to'liq deploy
│   └── rollback.sh             # oldingi versiyaga qaytish
└── README.deploy.md            # shu fayl

backend/Dockerfile.prod, backend/entrypoint.prod.sh
.github/workflows/deploy.yml
```

---

## 3. Serverga birinchi marta sozlash (bir marta bajariladi)

```bash
# 3.1. Docker + Compose plugin o'rnatish (Ubuntu)
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
```

```bash
# 3.2. Deploy foydalanuvchisini docker guruhiga qo'shish
sudo usermod -aG docker "$USER"
newgrp docker            # yoki qayta login qiling
docker run --rm hello-world   # tekshiruv
```

> **Telegram botga tegilmaydi.** Bot o'z konteyneri/servisida qoladi; biz uning
> konfiguratsiyasini, portini yoki tarmog'ini o'zgartirmaymiz.

---

## 4. Kodni serverga olish

```bash
cd ~                                   # yoki /opt/brandx
git clone <REPO_URL> brandx
cd brandx
chmod +x deploy/scripts/*.sh
```

---

## 5. `deploy/.env.prod` ni yaratish

```bash
cp deploy/.env.prod.example deploy/.env.prod
```

`deploy/.env.prod` faylini tahrirlang va **bo'sh qiymatlarni to'ldiring**.
Eng muhimlari:

```bash
# Bo'sh host portini tanlang (preflight.sh tekshiradi)
BRANDX_HTTP_BIND=127.0.0.1
BRANDX_HTTP_PORT=8080

# Maxfiy kalit (majburiy!)
SECRET_KEY=<python3 -c "import secrets; print(secrets.token_urlsafe(64))">DEBUG=False
ALLOWED_HOSTS=pos.example.com,localhost,127.0.0.1

CSRF_TRUSTED_ORIGINS=https://pos.example.com

DB_NAME=brandx
DB_USER=brandx
DB_PASSWORD=<kuchli-parol>

# HTTPS bilan ishlaganda True qiling
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False

# Faqat birinchi marta admin yaratish uchun (keyin false qilib qo'ying)
BOOTSTRAP_ADMIN=false
DJANGO_ADMIN_USERNAME=
DJANGO_ADMIN_PASSWORD=
DJANGO_ADMIN_PIN=
```

> `deploy/.env.prod` **git-ignored** — hech qachon commit qilinmaydi.

---

## 6. Preflight — port to'qnashuvini tekshirish

```bash
./deploy/scripts/preflight.sh
```

Chiqtida `ss -tulpn` ro'yxati ko'rinadi — bot va boshqa xizmatlar qaysi
portlarni egallagani ko'rsatiladi. Agar siz tanlagan `BRANDX_HTTP_PORT` band
bo'lsa, `.env.prod` da boshqa bo'sh port qo'ying (masalan `8090`, `8181`).

---

## 7. Testlarni Docker ichida ishga tushirish (deploy'dan oldin)

```bash
./deploy/scripts/test.sh
```

Bu skript:
1. **Production backend image**'ini quradi (deploy bilan **bir xil** image).
2. **Vaqtinchalik PostgreSQL** ni `tmpfs` (xotirada) ko'taradi — production
   ma'lumotlariga **umuman tegilmaydi**.
3. `makemigrations --check --dry-run` — yo'qolgan migratsiya bor-yo'qligini tekshiradi.
4. `manage.py check` — Django tizim tekshiruvi.
5. `manage.py test apps` — to'liq test to'plami.
6. Oxirida hammasini tozalaydi (volumes ham).

> Ishlab turgan BrandX stack'ga ham, botga ham ta'sir qilmaydi: alohida Docker
> project (`brandx-test`), alohida izolyatsiyalangan konteynerlar.

---

## 8. Birinchi deploy

```bash
./deploy/scripts/deploy.sh --skip-tests
```

- `--skip-tests` — chunki testlarni yuqorida qo'lda o'tkazdingiz (CI bo'lmasa).
- Skript: backup → image qurish → stack ko'tarish → hamma servis `healthy`
  bo'lguncha kutadi → keraksiz image'larni tozalaydi.

Holatni tekshirish:

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod ps
curl -s http://127.0.0.1:8080/health/          # → {"status":"ok","database":true}
```

### Birinchi admin (platform_admin) yaratish

Birinchi marta ishga tushirishda `.env.prod` da quyidagilarni o'rnating:

```bash
BOOTSTRAP_ADMIN=true
DJANGO_ADMIN_USERNAME=admin
DJANGO_ADMIN_PASSWORD=<kuchli-parol>
DJANGO_ADMIN_PIN=<4-8 raqam, oson topiladigan bo'lmasin>
```

Keyin `docker compose ... up -d backend` (yoki to'liq `deploy.sh`) ishlating va
admin yaratilgach, **`BOOTSTRAP_ADMIN=false`** qilib qo'ying (parol har restart'da
qayta o'rnatilmasligi uchun).

---

## 9. Host Nginx + HTTPS (bot yonida)

Serverda allaqachon nginx bo'lsa (bot webhook uchun), BrandX uchun **alohida**
server blok qo'shamiz:

```bash
sudo cp deploy/proxy/brandx.conf /etc/nginx/sites-available/brandx.conf
sudo nano /etc/nginx/sites-available/brandx.conf     # domeningizni yozing
sudo ln -s /etc/nginx/sites-available/brandx.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

HTTPS (bepul Let's Encrypt):

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d pos.example.com
```

Certbot HTTPS ishlagach, `deploy/.env.prod` da quyidagilarni yoqing:

```bash
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
```

va `./deploy/scripts/deploy.sh --skip-tests` bilan qayta ishga tushiring.

> Agar serverda nginx **yo'q** bo'lsa, `BRANDX_HTTP_BIND=0.0.0.0` qilib portni
> to'g'ridan-to'g'ri ochishingiz mumkin (TLS'siz — faqat ichki tarmoq uchun).

---

## 10. Kundalik yangilash (yangi versiya chiqarganda)

```bash
cd ~/brandx
git pull --ff-only
./deploy/scripts/deploy.sh          # test → backup → deploy
```

Yoki faqat kod yangilangan bo'lsa:

```bash
./deploy/scripts/deploy.sh --pull   # git pull'ni o'zi qiladi
```

---

## 11. Backup va Rollback

**Backup** (deploy avtomatik qiladi, lekin qo'lda ham mumkin):

```bash
./deploy/scripts/backup.sh
# natija: backups/db-<sana>.dump  va  backups/media-<sana>.tar.gz
```

**Rollback** (oxirgi deploy ishlamasa):

```bash
./deploy/scripts/rollback.sh        # oldingi image'larga qaytaradi
```

> Rollback **kodni** qaytaradi. Migratsiya bir tomonlama bo'lishi mumkin, shuning
> uchun kerak bo'lsa bazani qo'lda tiklang:
> `docker compose ... exec -T postgres pg_restore -U <user> -d <db> --clean < backups/db-XXX.dump`

---

## 12. GitHub Actions orqali avtomatik deploy

`.github/workflows/deploy.yml` tayyor. Repo → **Settings → Secrets and variables
→ Actions** ga quyidagi secret'larni qo'shing:

| Secret | Tavsif |
|--------|--------|
| `SSH_HOST` | Server IP/domeni |
| `SSH_USER` | SSH foydalanuvchi (docker guruhida) |
| `SSH_KEY` | Private SSH kalit (OpenSSH formati) |
| `SSH_PORT` | SSH port (ixtiyoriy, default 22) |
| `DEPLOY_PATH` | Serverdagi repo yo'li, masalan `/home/deploy/brandx` |

Endi `main` branch'ga har `push` qilganda: **test → (green bo'lsa) SSH orqali deploy**
avtomatik ishlaydi. `--pull` bayrog'i bilan `deploy.sh` serverda `git pull` qiladi.

> Serverdagi repo **public** bo'lmasa, deploy foydalanuvchisida read huquqi bo'lgan
> deploy key (yoki `git pull` uchun token) sozlang.

---

## 13. Telegram bot bilan to'qnashuv — tekshiruv ro'yxati

- [ ] `./deploy/scripts/preflight.sh` da `BRANDX_HTTP_PORT` **bo'sh**.
- [ ] Botning porti BrandX portidan **farq qiladi** (BrandX default `8080`).
- [ ] Bot **long polling** ishlatsa — keluvchi port yo'q, xavotir yo'q.
- [ ] Bot **webhook** ishlatib `80/443` ni egallagan bo'lsa — host nginx'ga
      BrandX uchun **alohida `server_name`** blok qo'shildi (botning blokiga
      tegilmadi).
- [ ] BrandX PostgreSQL hostda **port ochmaydi**, Django esa faqat loopback'da
      (`docker ps` da `backend` konteynerida `127.0.0.1:...` ko'rinadi).
- [ ] Bot va BrandX **turli Docker network**'da (BrandX: `brandx_prod_network`).

---

## 14. Foydali buyruqlar

```bash
# Compose qisqartmasi
alias bx='docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod'

bx ps                       # holat
bx logs -f backend          # Django loglari
bx restart backend          # bitta servisni qayta ishga tushirish
bx exec backend python manage.py shell

# Konteyner ichida testlar (production image bilan, qo'lda)
bx run --rm backend python manage.py test apps

# Django admin'ga kirish: http://<host>/admin/  (PIN bilan)
```

---

## 15. Xavfsizlik eslatmalari

- `SECRET_KEY` va barcha parollar **faqat** `deploy/.env.prod` da saqlanadi.
- Backend **root emas** (`appuser`, UID 10001) sifatida ishlaydi.
- PostgreSQL va Gunicorn hostga **ochilmagan**.
- `DEBUG=False` — stack trace tashqariga chiqmaydi.
- Log hajmi cheklangan (`max-size: 10m`, `max-file: 3`) — disk to'lib qolmaydi.
- HTTPS ishlagach, `SECURE_*` bayroqlarini yoqing (9-bo'lim).

---

## 16. Muammolarni bartaraf etish (troubleshooting)

| Belgi | Sabab / Yechim |
|-------|----------------|
| `port is already allocated` | `BRANDX_HTTP_PORT` band → boshqa port tanlang |
| 502 Bad Gateway (host nginx) | backend hali `healthy` emas: `bx logs backend` |
| Admin'ga kirib bo'lmaydi (HTTPS) | `CSRF_TRUSTED_ORIGINS`/`ALLOWED_HOSTS` ni domen bilan to'ldiring |
| Login ishlamaydi HTTPS'da | `SESSION_COOKIE_SECURE=True` ni faqat HTTPS borligida yoqing |
| Static fayllar 404 | `bx logs backend` da `collectstatic` o'tganini tekshiring |
| Media 404 | `backend` konteynerida `media_data` volume ulanmagan bo'lishi mumkin |

