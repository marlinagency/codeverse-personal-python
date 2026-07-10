def guvenli_bolme(a, b):
    try:
        return (a / b)
    except Exception as hata:
        hata = str(hata)
        print("hata yakalandi")
        return None
print(guvenli_bolme(10, 2))
print(guvenli_bolme(1, 0))
sayac = 0
while True:
    sayac = (sayac + 1)
    if (sayac >= 3):
        break
print(sayac)
toplam = 0
for i in range(1, 6):
    if ((i % 2) == 0):
        continue
    toplam = (toplam + i)
print(toplam)
