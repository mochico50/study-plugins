# study-plugins

学びを Claude に伴走してもらうためのプラグイン集です。入れ方、使い方、必要なものは、各プラグインの README にあります。

## プラグイン

| プラグイン | 内容 |
|---|---|
| [shikaku：資格勉強の伴走](plugins/shikaku/README.md) | 試験を調べて計画し、自分用のスケジュールを引き、毎回の学習を同じ形で回す |

## このリポジトリの作り

プラグインは `plugins/<名前>` の下にあり、それぞれが自分のバージョンとマニフェストを持ちます。入れられるプラグインの一覧は [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) に登録しています。

- [動作を確認した範囲](docs/compatibility.md)
- 変更したら `python3 scripts/validate.py` で、マニフェストとスキルの整合を確かめます（push と pull request のたびに CI でも実行されます）

## ライセンス

[MIT](LICENSE)
