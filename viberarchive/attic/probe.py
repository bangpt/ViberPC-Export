import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
for (t,) in con.execute("select name from sqlite_master where type='table' order by 1"):
    cols = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
    n = con.execute(f'select count(*) from "{t}"').fetchone()[0]
    print(t, n, cols)
print(con.execute("select min(TimeStamp), max(TimeStamp), count(*) from Events").fetchone())