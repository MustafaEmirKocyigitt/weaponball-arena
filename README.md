# Football Arena — günlük otomatik Reels

📅 **[Bugün ne paylaşılacak? → TODAY.md](TODAY.md)** · 📊 **[Taslak karşılaştırması → REPORT.md](REPORT.md)**

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

## 4 taslak (A/B testi)
Ana paylaşım her gün sırayla bir taslakla çıkar. Bonus slotlar kaydırmalı çalışır, böylece aynı gün farklı taslaklar görülür. Ayarlar `config.yaml` → `variants` bölümünde.

| Taslak | Açılış | Arena / ses | Süre |
|---|---|---|---|
| A · Classic | 2 sn intro kartı | lacivert, 128 BPM | ~28 sn (kontrol grubu) |
| B · Cold open | savaş ilk karede başlar + "WHO WINS TONIGHT?" | lacivert, 128 BPM | ~22 sn |
| C · Neon speed | cold open | neon mor/pembe ızgara, 140 BPM, tiz | ~17 sn |
| D · Lava | cold open | lav çatlakları, 118 BPM, kalın ses | ~18 sn |

Her paylaşımın taslağı ve Instagram media ID'si `data/history.json` dosyasına yazılır. **plan-and-report** workflow'u her sabah 06:00 UTC'de ve her paylaşımdan sonra çalışır:
- `TODAY.md`: günün planı (slot, saat, maç, taslak, tahmin)
- `REPORT.md`: taslak başına ortalama izlenme, **ortalama izlenme süresi**, beğeni, yorum, paylaşım, kaydetme

Kazanan netleşince (her taslakta ~5 paylaşım) `variants.rotation` listesine sadece kazananı bırakmak yeterli.

## Dakik zamanlama: cron-job.org (ücretsiz)
GitHub'ın kendi zamanlayıcısı saatlerce gecikebiliyor. Bu yüzden asıl tetikleyici olarak ücretsiz **cron-job.org** kullanılıyor; GitHub zamanlamaları yalnızca yedek. Aynı slot iki kez paylaşılmaz.

1. **GitHub token** — github.com → Settings → Developer settings → Fine-grained tokens → *Generate new token*
   - Repository access: *Only select repositories* → `weaponball-arena`
   - Permissions → Repository → **Actions: Read and write** (başka izin verme)
   - Süre: istediğin kadar (dolunca yenisini cron-job.org'a yapıştır)
2. **cron-job.org** → ücretsiz hesap → *Create cronjob*, üç tane:

| Başlık | Saat (Europe/Istanbul) | Body içindeki slot |
|---|---|---|
| weaponball early | her gün 14:00 | `early` |
| weaponball main | her gün **18:35** (video 19:00'da çıkar) | `main` |
| weaponball late | her gün 21:15 | `late` |

   Her birinde:
   - URL: `https://api.github.com/repos/MustafaEmirKocyigitt/weaponball-arena/actions/workflows/daily.yml/dispatches`
   - *Advanced* → Request method: **POST**
   - Headers: `Accept: application/vnd.github+json`, `Authorization: Bearer <TOKEN>`, `X-GitHub-Api-Version: 2022-11-28`
   - Body: `{"ref":"main","inputs":{"slot":"main","scheduled":"true"}}` (slot kısmını satıra göre değiştir)
   - Başarılı çağrı **204** döner.

## Zamanlama ve paylaşım sıklığı
**daily-arena** workflow'u günde 3 kez çalışır (UTC):

| Saat | Slot | Ne yapar |
|---|---|---|
| 11:00 | early | Sadece 11:45–15:10 arasında **büyük bir maç** başlıyorsa "bonus battle" paylaşır |
| 15:35 | **main** | Günün ana videosu, **her gün 16:00 UTC'de** (19:00 TR) paylaşılır. Maç yoksa Legends Clash |
| 18:15 | late | Sadece 19:00–22:25 arasında başka **büyük bir maç** başlıyorsa bonus battle paylaşır |

- Günde en fazla 3 paylaşım yapılır ve aynı maç asla iki kez paylaşılmaz.
- "Büyük maç" eşiği `config.yaml` → `schedule.bonus_min_score` (9) ile belirlenir. Kabaca büyük kulüp vs büyük kulüp, derbi ya da Şampiyonlar Ligi'nde büyük bir kulüp anlamına gelir. Sakin günlerde tek paylaşım yapılır.
- **Avrupa gecesi formatı:** Late slotun penceresinde 4 veya daha fazla Şampiyonlar Ligi ya da Avrupa Ligi maçı varsa tek bir "CHAMPIONS LEAGUE NIGHT" Reels'i çıkar. Bu video gecenin en büyük 3 maçını 5'er saniyelik mini savaşlarla gösterir, sonunda tahmin tablosu ve "HOW MANY WILL WE GET RIGHT?" çağrısı gelir. Toplam ~28 sn sürer. Ayarları `config.yaml` → `night` bölümünde.
- **Türk takımları Avrupa'da** ekstra puan alır (`selection.turkish_euro_bonus`).
- Elle çalıştırmak için: Actions → daily-arena → Run workflow (slot seç, `publish` işaretlenirse hemen paylaşır).

Notlar:
- Özel repoda ayda 2000 ücretsiz dakika var. Bu iş ayda yaklaşık 700–800 dakika kullanır: ana paylaşım ~20 dk/gün, bonus slotlar ~2–4 dk.
- ESPN API resmi değildir. ESPN erişilemezse sistem o gün "LEGENDS CLASH" videosu üretir, yani gün boş geçmez.
- Kulüp logoları tescilli marka olduğu için kullanılmıyor. Toplar takım renkleri ve kısa adlarla çiziliyor.
