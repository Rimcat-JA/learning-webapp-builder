# Learning Webapp Builder 1.0.0 — 検証結果

作成日：2026-09-19

## 完成した成果物

回答済みの要件シートに基づく、学習用Webアプリ作成AIスキル。スキル本文、共通データ形式、実行可能な参照採点・検証、既存教材の移行チェック、サンプル、使い方を収録した。

利用者の確定条件と、委任を受けて補った既定を`references/requirements.md`に分けて記録した。ホストや共有の設定は変更していない。

## 実施した検証

| 項目 | 結果 | 範囲 |
|---|---|---|
| 採点・教材・進捗の自動テスト | 44件 PASS | 六形式、未入力・不正型、数値の精度と許容誤差、未検証状態、履歴の正誤破損、旧版履歴 |
| 移行チェックの自動テスト | 34件 PASS | ID・版・参照、多対一対応の拒否、履歴保存、再採点禁止、入力ファイル上書き防止 |
| 合計 | **78件 PASS** | Python標準ライブラリで実行 |
| JSON Schema | PASS | Draft 2020-12のメタ検証、教材・進捗のサンプル適合、型不正の拒否 |
| サンプル教材・進捗 | PASS | 8問・二人分の進捗。未検証2問の警告は想定どおり |
| CLI採点 | PASS | `q-single`へ`opt-b`を回答し、graded・correct:true |
| CLI移行計画 | PASS | 同一教材の前後比較、進捗付きでready。元ファイルは不変 |
| 別ディレクトリからの実行 | PASS | 空白を含むパスへコピーしてテスト・検証・採点・移行を実行 |
| SKILL.md形式・相対リンク | PASS | YAMLのname／description、文書内のローカルリンク存在 |
| 要件レビュー | 反映済み | 構成案の確認を明文化し、承認済み・委任済み条件は聞き直さない規則を保持 |

実行環境はLinux、Python 3.12.14。JSON Schemaの独立検証には開発側でjsonschema 4.26.0を使用した。これは納品ツールの実行依存ではない。Windows実機上の実行検証は行っていない。

## テストが保証する範囲

付属スクリプトの処理と、サンプルを使った共通形式の動作を確認した。これからこのスキルを使って作るアプリの画面、ログイン、DB、外部同期が既に検証されたという意味ではない。それらはスキル内の完成基準に従い、生成するアプリごとに実装・実行検証する。

自然言語の問題の妥当性、出典の真偽、教育的な難易度はJSONの形式検査では保証できない。スキルは内容検証と記録を別工程として要求している。

同期サービスのアカウントやホスト先はこのスキルに組み込んでいない。作るアプリの条件に応じて設定し、未接続なら未接続と表示する設計を定めている。

## 再実行

展開後、`learning-webapp-builder`ディレクトリで実行する。

```powershell
py -3 -m unittest discover -s tests -v
py -3 scripts/course_tools.py validate examples/course.json --progress examples/progress.json --json
py -3 scripts/check_migration.py examples/course.json examples/course.json --progress examples/progress.json --output migration-plan.json
```

macOS／Linuxでは`py -3`を`python3`に置き換える。詳細ログは配布物の`validation/`に含む。

## 版管理と利用

Gitのタグ`v1.0.0`で記録し、Git bundleを同梱する。履歴を使う場合は`git clone learning-webapp-builder-v1.0.0.bundle learning-webapp-builder-source`で復元できる。

本成果物は受け取り後にAIへ読み込ませて使う。利用環境への自動登録やスキルの有効化は実行していない。最短の利用方法は`README.md`の依頼文を使い、`SKILL.md`を読ませること。
