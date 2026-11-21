# common_passwords.txt.gz

よく使われているパスワードの一覧（パスワードポリシーのチェックに使う）。

- 元データ: [SecLists](https://github.com/danielmiessler/SecLists)（MIT License）の
  `Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt`
  （英国 NCSC が Have I Been Pwned のデータから公開した、よく使われるパスワード上位10万件）
- 加工内容: 8〜128文字のものだけを残し、小文字にそろえ、重複を除いて並べ替え、gzip で圧縮
  （8文字未満は文字数のルールで弾くため不要）
- 件数: 46,483 件

一覧を更新するときは、元データをダウンロードして同じ加工をすること。
