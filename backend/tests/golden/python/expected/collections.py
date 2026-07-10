skorlar = {"jett": 10, "sage": 5}
skorlar["omen"] = 8
print(len(skorlar))
print(skorlar.get("jett"))
if ("sage" in skorlar):
    print("sage takimda")
del skorlar["sage"]
print(list(skorlar.keys()))
print(list(skorlar.values()))
liste = [3, 1]
liste.append(2)
liste.remove(3)
print(liste)
print(liste[0])
print(len(liste))
liste[0] = 9
print(liste)
