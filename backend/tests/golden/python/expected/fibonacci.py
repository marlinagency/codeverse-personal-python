def fib(n):
    if (n <= 1):
        return n
    return (fib((n - 1)) + fib((n - 2)))
sonuclar = []
for i in range(10):
    sonuclar.append(fib(i))
print(sonuclar)
