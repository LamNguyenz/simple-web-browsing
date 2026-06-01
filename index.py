def main():
    arr = [1, 2, [4]]
    out1 = recursive(arr, [])
    out2 = recursive(arr, [])
    print("Out 1: ", out1)
    print("Out 2: ", out2)


def recursive(arr, out):
    if not out:
        out = []
    for child in arr:
        if isinstance(child, list):
            recursive(child, out)
        else:
            out.append(child)
    return out


main()
