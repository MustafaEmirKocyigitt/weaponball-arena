# Football Arena — günlük otomatik Reels

**@weaponball.fc**: Her gün Süper Lig, 5 büyük lig, Şampiyonlar Ligi ve Avrupa Ligi maçlarından en popüler olanını seçer. İki takım arenada savaştırılır ve video her akşam 19:00'da (TR) Instagram'a Reels olarak yüklenir. **Günlük çalışırken hiç LLM/token kullanmaz**, her şey deterministik koddur.

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

## Instagram bağlantısı (kuruldu)
- Meta uygulaması **weaponball-arena** → Weaponball business portfolio → sistem kullanıcısı **WeaponballBot**.
- WeaponballBot'a atananlar: uygulama (tam kontrol) ve @weaponball.fc (İçerik + İstatistikler). Token süresi **asla dolmaz**; izinleri `instagram_basic`, `instagram_content_publish`, `instagram_manage_insights`.
- API: `graph.facebook.com`. Instagram hesap ID'si `config.yaml` → `instagram.user_id` (17841449071564126).
- GitHub secret: yalnızca `IG_ACCESS_TOKEN`. Token'ı kontrol etmek için Actions → **check-instagram-token** → Run workflow.
- Token'ı iptal etmek veya yenilemek için: Meta Business Suite → Ayarlar → Sistem kullanıcıları → WeaponballBot → Jetonları geri çek / Jeton oluştur.

## Zamanlama ve paylaşım sıklığı
**daily-arena** workflow'u günde 3 kez çalışır (UTC):

| Saat | Slot | Ne yapar |
|---|---|---|
| 11:00 | early | Sadece 11:45–15:10 arasında **büyük bir maç** başlıyorsa "bonus battle" paylaşır |
| 15:35 | **main** | Günün ana videosu, **her gün 16:00 UTC'de** (19:00 TR) paylaşılır. Maç yoksa Legends Clash |
| 18:15 | late | Sadece 19:00–22:25 arasında başka **büyük bir maç** başlıyorsa bonus battle paylaşır |

- Günde en fazla 3 paylaşım yapılır ve aynı maç asla iki kez paylaşılmaz.
- "Büyük maç" eşiği `config.yaml` → `schedule.bonus_min_score` (9) ile belirlenir. Kabaca büyük kulüp vs büyük kulüp, derbi ya da Şampiyonlar Ligi'nde büyük bir kulüp anlamına gelir. Sakin günlerde tek paylaşım yapılır.
- Elle çalıştırmak için: Actions → daily-arena → Run workflow (slot seç, `publish` işaretlenirse hemen paylaşır).

Notlar:
- Özel repoda ayda 2000 ücretsiz dakika var. Bu iş ayda yaklaşık 700–800 dakika kullanır: ana paylaşım ~20 dk/gün, bonus slotlar ~2–4 dk.
- ESPN API resmi değildir. ESPN erişilemezse sistem o gün "LEGENDS CLASH" videosu üretir, yani gün boş geçmez.
- Kulüp logoları tescilli marka olduğu için kullanılmıyor. Toplar takım renkleri ve kısa adlarla çiziliyor.
