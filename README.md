# SVG → Font Converter

Canva'dan SVG export et → TTF + OTF olarak indir.

## Kurulum

Python 3.8+ gerekli. Bağımlılıkları kur:

```bash
pip install fonttools lxml
```

## Çalıştırma

```bash
python3 app.py
```

Sonra tarayıcında aç: **http://localhost:5000**

## Kullanım

### 1. Canva'da SVG hazırla
- Yeni bir sayfa aç
- Tüm karakterleri yaz: **A B C ... Z a b c ... z 0-9 . , ! ? ...**
- Her karakteri **ayrı bir text objesi** yap
- Soldan sağa, yukarıdan aşağıya sırala
- **File → Download → SVG** olarak indir

### 2. Converter'da
1. SVG'yi yükle
2. Font adını gir
3. Regular / Bold / Italic / Bold Italic seç
4. **FONTU OLUŞTUR** tıkla
5. TTF + OTF olarak indir

## Komut Satırı Kullanımı

```bash
# Regular
python3 engine.py harfler.svg --name "BalonYazi" --output ./output

# Bold
python3 engine.py harfler.svg --name "BalonYazi" --bold --output ./output

# Italic  
python3 engine.py harfler.svg --name "BalonYazi" --italic --output ./output
```

## Karakter Sırası

SVG'deki nesneler soldan sağa, yukarıdan aşağıya sıralanır ve şu karakterlere atanır:

```
A B C D E F G H I J K L M N O P Q R S T U V W X Y Z
a b c d e f g h i j k l m n o p q r s t u v w x y z
0 1 2 3 4 5 6 7 8 9
. , ! ? ; : ' " ( ) - _ / @ # $ % & * + =
Ç Ğ İ Ö Ş Ü ç ğ ı ö ş ü
```

Web arayüzünde bu sırayı özelleştirebilirsin.

## Sorunlar

**"path bulunamadı" hatası:**
- Canva'dan SVG export ederken "Flatten" seçeneğini kapat
- Her karakterin kendi path'i olduğundan emin ol

**Karakterler karışık çıkıyor:**
- SVG'de karakterleri düzenli grid'e yerleştir
- Her satırda eşit yükseklikte hizala
