import discord
from discord.ext import commands
import asyncio
from datetime import datetime

# --- AYARLAR ---
LOG_KANAL_ID = 1505277299409293403  # Logların gönderileceği kanalın ID'sini yazın
YETKILI_ROL_ID = 1505277299409293403 # Yetkili ekibin rol ID'sini yazın (Opsiyonel, yoksa None yapın)

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


# --- 2. TICKET KAPATMA BUTONU ---
class TicketKapatButonu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Bileti Kapat", style=discord.ButtonStyle.danger, custom_id="bilet_kapat", emoji="🔒")
    async def bilet_kapat(self, interaction: discord.Interaction, button: discord.ui.Button):
        kapatan = interaction.user
        guild = interaction.guild
        kanal_adi = interaction.channel.name

        await interaction.response.send_message("Bu bilet kanalı 5 saniye içinde siliniyor...", ephemeral=False)

        # --- LOG KANALINA BİLDİRİM (KAPANIŞ) ---
        log_kanali = guild.get_channel(LOG_KANAL_ID)
        if log_kanali:
            log_embed = discord.Embed(
                title="🔴 Destek Talebi Kapatıldı",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            log_embed.add_field(name="Kapatılan Kanal", value=f"`#{kanal_adi}`", inline=False)
            log_embed.add_field(name="Kilitleyen / Kapatan", value=f"{kapatan.mention} (`{kapatan.id}`)", inline=False)
            log_embed.set_thumbnail(url=kapatan.display_avatar.url)
            await log_kanali.send(embed=log_embed)

        await asyncio.sleep(5)
        await interaction.channel.delete()


# --- 3. BİLET AÇMA BUTONU (GİRİŞ PANELİ) ---
class TicketKurulumButonu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Destek Talebi Aç", style=discord.ButtonStyle.success, custom_id="bilet_ac", emoji="🎫")
    async def bilet_ac(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Butona basınca sebep soran modal (pencere) açılır
        await interaction.response.send_modal(TicketSebepModal())


# --- BOT OLAYLARI (EVENTS) ---
@bot.event
async def on_ready():
    # Persistent view kayıtları (Bot yeniden başlasa da butonlar çalışır)
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

# Bot Tokeninizi buraya yazın
bot.run('MTU0NjI1Mzc3NzE3NzE1MzU5OQ.GDT-s2.XhOJ6eoNvnqiVQXYC6VfNSiv8YlZu3ugdq3vl8')