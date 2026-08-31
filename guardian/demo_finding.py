import sys
sys.path.insert(0, ".")
import guardian_app as g

g.settings["running"] = False
g.findings.append({
    "value": "Вложите всего 50 000 тенге и уже через неделю получите (схема «вложи сейчас → получи потом»)",
    "window": "Telegram", "score": None,
    "flags": "", "flag_list": [], "kind": "phrase", "sources": 0, "at": "01:27:00",
})
g.findings.append({
    "value": "profit-guarantee.top", "window": "Google Chrome", "score": 82,
    "flags": "домен свежерегистрирован, дешёвая TLD-зона",
    "flag_list": ["домен свежерегистрирован (6 дн. назад)",
                  "дешёвая TLD-зона, типичная для скам-инфраструктуры",
                  "маркер-приманка в имени домена", "нет истории в веб-архиве"],
    "kind": "domain", "sources": 9, "at": "01:28:11",
})
g.state["checked"] = 14
g.state["flagged"] = 2
g.state["window"] = "Telegram"
g.notify("SAQ Guardian — обнаружен риск", "profit-guarantee.top: risk-score 82/100")
g.main()
