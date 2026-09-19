# 共通データ形式と採点API

正確な構造は`schemas/`、動く例は`examples/`が基準。JSON Schemaは構造、`course_tools.py`は参照・型・候補所属・有限数値・学習履歴等の追加検証を担当する。任意のアプリ内形式から変換する場合、往復で情報が失われないことを確かめる。

## 教材

`schemaVersion`は契約の版、`version`は教材の版。`id`は教材の安定ID。対象者、前提知識、目標、章と問題を持つ。各問題は一つの章の`questionIds`に一度だけ所属し、問題側の`chapterId`と一致する。表示順を変えてもIDを変えない。

問題の`revision`は1以上の整数。`difficulty`は1〜10。`explanation`は`summary`と`correctReason`を持つ。選択肢の`explanation`はその候補が正しい／誤りである理由を説明する。教材固有のメタデータは拡張可能だが、未知の採点方式を既存タイプとして黙って採点しない。

| type | 問題固有の項目 | answer |
|---|---|---|
| `single_choice` | `options:[{id,text,explanation}]` | 選択肢ID文字列 |
| `multiple_choice` | 同上 | 重複のないID配列。順不同 |
| `numeric` | `scoring`は任意。許容誤差を指定 | 有限数値または半角数値文字列 |
| `cloze_select` | `slots:[{id,label,options}]` | `{slotId:optionId}`。全slot必須 |
| `ordering` | `options:[{id,text,explanation}]` | 全IDを含む正しい順序の配列 |
| `matching` | `items:[{id,text}]`と`options` | `{itemId:optionId}`。左右一対一の全対応 |

数値の`scoring`は`absoluteTolerance`と`relativeTolerance`のみ。省略時はどちらも0。判定は`|回答−正答| ≤ max(絶対許容誤差, 相対許容誤差 × |正答|)`。端数処理を問題文に明記し、範囲が広すぎて誤答が正答になることも確認する。文字列の前後空白は除去する。200文字以内、指数の絶対的な大きさは実装の許容範囲内に限る。採点器は全角数字や単位を推測変換しない。

`verification`は`status:verified|unverified`と`evidence`配列。verifiedは正答と根拠を必須にする。unverifiedは`reason`を必須にし、正答が未確定なら`answer`キーを省略する。`null`を正答未確定の代用にしない。`hint`は必要なときだけ`{text,rationale,trigger:"on_request"}`を付ける。

## 参照採点の結果

Pythonからは`grade_question(question, answer)`を呼ぶ。事前に教材全体を`validate_course`で検証する。外部から未検証の問題オブジェクトをそのまま渡すAPIではない。

| status | correct | countsTowardMastery | アプリの表示 |
|---|---|---|---|
| `graded` | true／false | true | 正解／不正解 |
| `provisional` | true／false | false | 未検証・暫定採点 |
| `pending` | null | false | 未検証・採点保留 |
| `invalid` | null | false | 入力を直す案内。回答履歴にしない |

誤答も検証済み問題の成績の分母に入るため、`countsTowardMastery:true`は「正解」ではなく「確定評価の対象」を意味する。習得度の集計ではさらに現行revisionかを確認する。採点結果は解説全体と正答を返すので、模擬試験では提出後に開示する。

## 進捗の交換形式

`learners`は学習者の一覧であり、認証情報を含まない。`attempts`はID付きの追記履歴、`bookmarks`は学習者と問題の組の現在一覧。

回答履歴には`id,learnerId,questionId,questionRevision,answer,correct,at,mode,status,countsTowardMastery`を持たせる。`at`は秒とタイムゾーンのあるISO形式、`mode`は`practice|review|mock`。例は`2026-01-01T09:00:00+09:00`。

旧revisionの履歴は現在の正解で再採点せず警告付きで保持する。未来のrevision、未知の問題、重複履歴ID、他の教材IDは拒否する。教材versionが違う場合の警告だけで取り込みを許可せず、旧版と新版による移行計画を通す。

模擬試験の未回答は提出セッションの未回答欄として保持し、通常の有効な回答イベントへ偽装しない。期限、問題順、同期キュー、ブックマーク解除操作等のアプリ内部データは共通交換形式の基本項目以外に設計する。

旧形式にstatus等がない場合は移行アダプターで当時の問題版と検証状態から明示的に補う。推定根拠がない正誤をverifiedとして補完しない。

## CLI終了コード

`course_tools.py validate`: 0＝検証成功、1＝データ不適合、2＝JSON／I/O／実行エラー。警告は成功と両立する。

`course_tools.py grade`: 0＝graded/provisional/pendingの結果を返した、1＝教材不適合、2＝回答不適合や実行エラー。**不正解は終了コード0**で`correct:false`となる。

`check_migration.py`: 0＝計画可能、1＝停止理由あり、2＝入力／実行エラー。計画可能でも実データの移行は実施されない。
