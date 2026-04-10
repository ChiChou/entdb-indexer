import sys

with open(sys.argv[1], "r") as fp:
    content = fp.read()

sys.stderr.write("submit the list to https://theapplewiki.com/wiki/Special:Export\n")

begin = "[[Keys:"
end = "]]"

cursor = 0
while True:
    begin_idx = content.find(begin, cursor)
    if begin_idx == -1:
        break

    end_idx = content.find(end, begin_idx)
    if end_idx == -1:
        break

    between = content[begin_idx + len(begin) : end_idx]
    print("Keys:" + between[0 : between.find("|")])

    cursor = end_idx + len(end)
