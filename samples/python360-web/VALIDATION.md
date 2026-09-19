# ローカル版の検証

確認日: 2026-09-18

## 機能

- 36章・360問。数値251問・単一選択109問、正解・解説・ヒントの対応を確認。
- 全360問の正解・誤答・空入力、整数の正規化、初回回答を保持した再回答、バックアップ検査を確認。
- 同梱Pythonサーバー上で、主要16シナリオのブラウザテストが成功。
- 同梱Node.jsサーバーでも数値・選択式の採点、進捗、再読み込みを確認。

## サーバー

- python: real server, correct asset types, all 360 questions, HEAD, no directory listing, path/host restrictions
- python: repeated start reuses same origin and existing server
- Python localhost: full 16-scenario browser suite against the actual packaged server
- python: occupied port reports a clear error without changing ports
- node: real server, correct asset types, all 360 questions, HEAD, no directory listing, path/host restrictions
- node: repeated start reuses same origin and existing server
- Node localhost: numeric/choice grading and persistence through page reload
- node: occupied port reports a clear error without changing ports
- Node.jsの二重起動検出はIPv4の明示指定後にも再確認済み。

## 確認範囲

Linux上のPython 3.12とNode.js 24、Chromiumで実行。Windowsのstart.batは付属しますが、Windows実機でのダブルクリックはこの環境では未検証です。両サーバーはランタイム標準機能のみを使用します。

画面はホスト版から引き継いだものです。サーバーは127.0.0.1のみで待ち受けます。進捗の保存先はブラウザであり、ホスト版からはバックアップの読み込みが必要です。
