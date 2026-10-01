import os
import secrets
import json
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import discord
from discord.ext import commands
import mysql.connector

# --- RENDER İÇİN MİNİMAL HTTP SUNUCUSU ---
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot aktif!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_http_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# HTTP sunucusunu arka planda başlat
threading.Thread(target=run_http_server, daemon=True).start()

# --- AYARLAR VE ÇEVRE DEĞİŞKENLERİ ---
LOG_KANAL_ID = 1505277299409293403  # Logların gönderileceği kanalın ID'si
YETKILI_ROL_ID = 1505277299409293403 # Yetkili ekibin rol ID'si

SITE_URL = os.getenv("SITE_URL", "https://krytexnetwork.com.tr")
DB_HOST = os.getenv("DB_HOST", "cpanel-c1.leaderos.com.tr")
DB_USER = os.getenv("DB_USER", "user6423")
DB_PASS = os.getenv("DB_PASS", "dn245$r$TDBt ")
DB_NAME = os.getenv("DB_NAME", "user6423")

# --- VERİTABANI YARDIMCI FONKSİYONU ---
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            charset='utf8mb4'
        )
        return conn
    except Exception as e:
        print(f"Veritabanı bağlantı hatası: {e}")
        return None

# Bot kurulumu
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="k!", intents=intents)

# --- 1. SEBEP SORAN MODAL (FORM) ---
class TicketSebepModal(discord.ui.Modal, title="Destek Talebi Oluştur"):
    sebep = discord.ui.TextInput(
        label="Destek alma sebebiniz nedir?",
        style=discord.TextStyle.paragraph,
        placeholder="Lütfen sorununuzu veya talebinizi kısaca açıklayın...",
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        kullanici = interaction.user

        # Bilet izinleri
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            kullanici: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        # Eğer Yetkili Rol ID tanımlandıysa izne ekle
        if YETKILI_ROL_ID:
            yetkili_rol = guild.get_role(YETKILI_ROL_ID)
            if yetkili_rol:
                overwrites[yetkili_rol] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        # Bilet kanalını oluştur
        bilet_kanali = await guild.create_text_channel(
            name=f"bilet-{kullanici.name}",
            overwrites=overwrites,
            topic=f"{kullanici.id} ID'li kullanıcının destek talebi."
        )

        # Kullanıcıya sadece kendisinin göreceği onay mesajı
        await interaction.response.send_message(f"Biletiniz başarıyla oluşturuldu: {bilet_kanali.mention}", ephemeral=True)

        # Bilet kanalının içine hoş geldin mesajı ve kapatma butonu
        embed = discord.Embed(
            title="🎫 Destek Talebi",
            description=f"Merhaba {kullanici.mention}, destek ekibimiz en kısa sürede size yardımcı olacaktır.\n\n**Talep Sebebi:**\n```{self.sebep.value}```\nİşiniz bittiğinde biletinizi kapatmak için aşağıdaki **Bileti Kapat** butonuna tıklayabilirsiniz.",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        await bilet_kanali.send(embed=embed, view=TicketKapatButonu())

        # --- LOG KANALINA BİLDİRİM (AÇILIŞ) ---
        log_kanali = guild.get_channel(LOG_KANAL_ID)
        if log_kanali:
            log_embed = discord.Embed(
                title="🟢 Yeni Destek Talebi Açıldı",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            log_embed.add_field(name="Açan Kullanıcı", value=f"{kullanici.mention} (`{kullanici.id}`)", inline=False)
            log_embed.add_field(name="Bilet Kanalı", value=f"{bilet_kanali.mention}", inline=False)
            log_embed.add_field(name="Açılış Sebebi", value=f"```{self.sebep.value}```", inline=False)
            log_embed.set_thumbnail(url=kullanici.display_avatar.url)
            await log_kanali.send(embed=log_embed)


# --- 2. TICKET KAPATMA BUTONU VE TRANSCRIPT KAYDI ---
class TicketKapatButonu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Bileti Kapat", style=discord.ButtonStyle.danger, custom_id="bilet_kapat", emoji="🔒")
    async def bilet_kapat(self, interaction: discord.Interaction, button: discord.ui.Button):
        kapatan = interaction.user
        guild = interaction.guild
        kanal = interaction.channel
        kanal_adi = kanal.name

        await interaction.response.send_message("Bilet kapatılıyor ve mesaj geçmişi veritabanına kaydediliyor...", ephemeral=False)

        # 1. KANALDAKİ MESAJLARI TOPLA
        mesaj_listesi = []
        async for msg in kanal.history(limit=500, oldest_first=True):
            mesaj_listesi.append({
                "yazar": str(msg.author),
                "avatar": str(msg.author.display_avatar.url),
                "bot": msg.author.bot,
                "zaman": msg.created_at.strftime("%d.%m.%Y %H:%M"),
                "icerik": msg.content or "[İçerik/Görsel Mesajı]"
            })

        # 2. GÜVENLİ TOKEN VE TICKET ID ÜRET
        ticket_id = str(kanal.id)
        token = secrets.token_urlsafe(32)

        # Kullanıcı ID'sini kanal konusundan çekmeye çalış (yoksa varsayılan al)
        kullanici_id = "0"
        if kanal.topic and "ID'li" in kanal.topic:
            kullanici_id = kanal.topic.split(" ")[0]

        # 3. VERİTABANINA KAYDET
        conn = get_db_connection()
        transcript_url = None
        if conn:
            try:
                cursor = conn.cursor()
                sql = """
                INSERT INTO discord_transcripts (ticket_id, token, kullanici_id, kullanici_adi, mesajlar)
                VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (
                    ticket_id,
                    token,
                    kullanici_id,
                    kanal_adi,
                    json.dumps(mesaj_listesi, ensure_ascii=False)
                ))
                conn.commit()
                cursor.close()
                conn.close()

                transcript_url = f"{SITE_URL.rstrip('/')}/transcript.php?id={ticket_id}&token={token}"
            except Exception as e:
                print(f"Veritabanı kayıt hatası: {e}")

        # 4. LOG KANALINA VE KULLANICIYA BİLDİRİM
        log_kanali = guild.get_channel(LOG_KANAL_ID)
        if log_kanali:
            log_embed = discord.Embed(
                title="🔴 Destek Talebi Kapatıldı",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            log_embed.add_field(name="Kapatılan Kanal", value=f"`#{kanal_adi}`", inline=False)
            log_embed.add_field(name="Kilitleyen / Kapatan", value=f"{kapatan.mention} (`{kapatan.id}`)", inline=False)
            if transcript_url:
                log_embed.add_field(name="🌐 Web Transkripti", value=f"[Geçmişi Görüntüle]({transcript_url})", inline=False)
            log_embed.set_thumbnail(url=kapatan.display_avatar.url)
            await log_kanali.send(embed=log_embed)

        # Kapatan kişiye DM ile transkript linki gönder
        if transcript_url:
            try:
                dm_embed = discord.Embed(
                    title="🎫 Biletiniz Kapatıldı",
                    description=f"Kapatılan Bilet: `#{kanal_adi}`\n\nDestek talebinizin mesaj geçmişini web sitemiz üzerinden inceleyebilirsiniz:\n[Bilet Geçmişini Aç]({transcript_url})",
                    color=discord.Color.blue()
                )
                await kapatan.send(embed=dm_embed)
            except Exception:
                pass  # DM kapalıysa hata vermesin

        await asyncio.sleep(3)
        await kanal.delete()


# --- 3. BİLET AÇMA BUTONU (GİRİŞ PANELİ) ---
class TicketKurulumButonu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Destek Talebi Aç", style=discord.ButtonStyle.success, custom_id="bilet_ac", emoji="🎫")
    async def bilet_ac(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketSebepModal())


# --- BOT OLAYLARI (EVENTS) ---
@bot.event
async def on_ready():
    bot.add_view(TicketKurulumButonu())
    bot.add_view(TicketKapatButonu())
    print(f"{bot.user} olarak giriş yapıldı ve Bilet Sistemi aktif!")


# --- BOT KOMUTLARI ---
@bot.command()
@commands.has_permissions(administrator=True)
async def ticket_kur(ctx):
    embed = discord.Embed(
        title="🛠️ Destek ve Yardım Merkezi",
        description="Bizimle iletişime geçmek ve bir destek talebi (ticket) oluşturmak için aşağıdaki **Destek Talebi Aç** butonuna tıklayın.",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed, view=TicketKurulumButonu())
    await ctx.message.delete()

# Token ortam değişkeninden (Environment Variable) okunur
token = os.getenv("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("HATA: 'DISCORD_TOKEN' ortam değişkeni bulunamadı. Lütfen Render ayarlarından ekleyin.")
