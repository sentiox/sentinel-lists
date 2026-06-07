# Sentinel Lists

Актуальные списки доменов и подсетей для HarpyNet, sing-box, Mihomo,
dnsmasq, ClashX, MikroTik и других систем маршрутизации.

Репозиторий автоматически обновляет списки и выпускает готовые форматы:

- RAW
- SRS для sing-box
- MRS для Mihomo
- Xray DAT
- dnsmasq ipset и nftset
- ClashX, Kvas и MikroTik

## Сервисы

- Discord, включая IP-диапазоны голосовых relay-серверов
- Telegram, включая DC и media-подсети
- Google Meet
- YouTube, Google AI и Google Play
- Meta, Twitter, TikTok и Roblox
- Cloudflare, CloudFront, DigitalOcean, Hetzner и OVH

## Прямые ссылки

- [Discord domains](https://raw.githubusercontent.com/sentiox/sentinel-lists/main/Services/discord.lst)
- [Discord IPv4](https://raw.githubusercontent.com/sentiox/sentinel-lists/main/Subnets/IPv4/discord.lst)
- [Telegram domains](https://raw.githubusercontent.com/sentiox/sentinel-lists/main/Services/telegram.lst)
- [Telegram IPv4](https://raw.githubusercontent.com/sentiox/sentinel-lists/main/Subnets/IPv4/telegram.lst)
- [Russia inside](https://raw.githubusercontent.com/sentiox/sentinel-lists/main/Russia/inside-raw.lst)
- [Russia outside](https://raw.githubusercontent.com/sentiox/sentinel-lists/main/Russia/outside-raw.lst)

Готовые SRS, MRS и DAT публикуются в разделе
[Releases](https://github.com/sentiox/sentinel-lists/releases).

## Обновление

- Доменные списки собираются раз в неделю и при изменении исходников.
- Подсети обновляются по средам и воскресеньям.
- Workflow можно запустить вручную из GitHub Actions.

Проект развивает команда Sentinel/HarpyNet. При обновлении источников
сохраняются дополнительные fallback-диапазоны Discord voice и Telegram,
чтобы временные ошибки внешних API не ломали голосовую связь и медиа.
