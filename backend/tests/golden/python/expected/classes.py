class Oyuncu:
    def __init__(self, isim="bilinmeyen", puan=0):
        self.isim = isim
        self.puan = puan
    def puan_ekle(self, eklenecek):
        self.puan = (self.puan + eklenecek)
        return self.puan
o = Oyuncu("jett", 3)
o.puan_ekle(5)
print(o.isim)
print(o.puan)
