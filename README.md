# Football Arena — günlük otomatik Reels

**@weaponball.fc**: Her gün 6 ligin (Süper Lig, Premier League, LaLiga, Bundesliga, Serie A, Ligue 1) maçlarından en popüler olanını seçer. İki takım arenada savaştırılır ve video her akşam 19:00'da (TR) Instagram'a Reels olarak yüklenir. **Günlük çalışırken hiç LLM/token kullanmaz**, her şey deterministik koddur.

```
ESPN fikstür + puan durumu → maç seçimi → güç / kazanma olasılığı
  → director (300 savaş simüle eder, en dramatiğini seçer)
  → render (pygame) + prosedürel ses (numpy) → ffmpeg MP4
  → İngilizce caption → Instagram API (19:00'da yayın)
```

## Yerelde çalıştırma
```powershell
py -3.13 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\arena preview --home Galatasaray --away Fenerbahce --home-strength 0.7 --away-strength 0.6
.venv\Scripts\arena daily                      # bugünün videosu -> output\YYYY-MM-DD\
.venv\Scripts\arena daily --date 2026-11-29
.venv\Scripts\arena publish --dir output\2026-11-29 --dry-run
.venv\Scripts\python -m pytest
```

## Tahmin geçmişi
Her paylaşılan tahmin `data/history.json` dosyasına yazılır. Ertesi gün maçın gerçek skoru ESPN'den çekilir ve açıklamaya şu satır eklenir: `Last call ✅ Arsenal (ARS 2-1 MCI) · Arena record: 7/10`. En az 3 sonuçlanmış tahmin olduktan sonra kazanan kartında `ARENA RECORD 7/10` da görünür. GitHub workflow bu dosyayı her gün repoya commit'ler.

## Müzik
Arka plan müziği kodla üretilir (`src/arena/audio/music.py`): 128 BPM, kick, clap, bas ve arpej. Telif sorunu yoktur. Arena daralmaya başlayınca müzik yoğunlaşır, KO'da durur. İstersen `assets/music/` klasörüne kendi telifsiz parçanı da koyabilirsin, efektlerin altına karıştırılır.

## Ayarlar
- `config.yaml`: Ligler, maç seçim ağırlıkları, derbiler, "legends" yedek eşleşmeleri, video/ses ayarları, paylaşım saati ve `brand` (şu an `@weaponball.fc`).
- `data/teams.yaml`: Takım renkleri, kısa adları, silahları ve "büyük kulüp" işareti.
- `assets/fonts/`: Anton (başlıklar) ve Oswald (etiketler) burada. İkisi de OFL lisanslı, lisans dosyaları yanlarında.

## GitHub Actions kurulumu (bir kez)
1. Bu klasörü **özel (private)** bir GitHub reposuna yükle.
2. Instagram hesabını **Profesyonel** (İşletme veya İçerik Üreticisi) hesaba çevir.
3. https://developers.facebook.com adresinde bir uygulama oluştur:
   - Ürün olarak **Instagram → "API setup with Instagram login"** ekle.
   - Kendi Instagram hesabını ekleyip izinleri ver: `instagram_business_basic`, `instagram_business_content_publish`.
   - "Generate token" ile **long-lived access token** al.
   - Sadece kendi hesabına paylaşım yapacağın için App Review gerekmez.
4. Repo → Settings → Secrets and variables → Actions bölümüne şunları ekle:
   - `IG_ACCESS_TOKEN`: Aldığın token.
   - `IG_USER_ID`: Instagram kullanıcı ID'si (opsiyonel, boş bırakırsan `me` kullanılır).
   - `GH_PAT`: Sadece bu repo için **Secrets: Read and write** yetkisi olan fine-grained token. Instagram token'ını haftalık yenilemek için gerekiyor.
5. Actions → **daily-arena** → "Run workflow" (`publish` kapalı) ile önce kuru deneme yap. Videoyu Artifacts bölümünden indirip izle.
6. Hazır olduğunda `publish` açık şekilde bir kez çalıştır. Ondan sonra her gün 18:20'de (TR) kendiliğinden çalışır ve 19:00'da paylaşır.

Notlar:
- Özel repoda ayda 2000 ücretsiz dakika var, bu iş günde ~40 dakika (render + 19:00'ı bekleme) kullanır. Açık (public) repoda dakika sınırsızdır, ama GitHub 60 gün commit yapılmayan public repolarda zamanlanmış işleri durdurur.
- ESPN API resmi değildir. ESPN erişilemezse sistem o gün "LEGENDS CLASH" videosu üretir, yani gün boş geçmez.
- Kulüp logoları tescilli marka olduğu için kullanılmıyor. Toplar takım renkleri ve kısa adlarla çiziliyor.
