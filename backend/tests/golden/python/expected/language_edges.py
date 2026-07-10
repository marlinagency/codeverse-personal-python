import math
def classify(x, label="agent"):
    if ((x > 10) and (label is not None)):
        print((label + ": high"))
    elif ((x == 10) or (not False)):
        print("ten")
    else:
        print("low")
    return None
values = [1, 2]
try:
    print("probe ok")
finally:
    print("cleanup")
classify(12, "jett")
classify(10)
classify(3)
print(math.sqrt(16))
print(values)
