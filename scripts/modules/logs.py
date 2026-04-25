import datetime
import json as js


class Logs:
    def __init__(self):
        pass

    def createLog(self):
        with open("data/logs.json", "w") as f:
            init = {"users": {}}

            js.dump(init, f)

    def addAlert(self, id, code, alert, url):
        try:
            with open("data/logs.json", "r+") as f:
                data = js.load(f)
                if str(id) not in data["users"]:
                    data["users"][str(id)] = []

                data["users"][str(id)].append(
                    {
                        "code": code,
                        "timestamp": datetime.datetime.now().strftime(
                            "%H:%M:%S | %d-%m-%Y"
                        ),
                        "alert": alert,
                        "url": url,
                    }
                )
                f.seek(0)
                js.dump(data, f, indent=4)
                f.truncate()
        except FileNotFoundError:
            self.createLog()
            self.addAlert()

    def removeAlert(self, id, code):
        try:
            with open("data/logs.json", "r+") as f:
                data = js.load(f)
                if str(id) in data["users"]:
                    data["users"][str(id)] = [
                        alert
                        for alert in data["users"][str(id)]
                        if alert["code"] != code
                    ]
                    f.seek(0)
                    js.dump(data, f, indent=4)
                    f.truncate()
        except FileNotFoundError:
            self.createLog()

    def listUsers(self):
        try:
            with open("data/logs.json", "r") as f:
                data = js.load(f)

                users = []
                for user, alerts in data["users"].items():
                    users.append((user, alerts))

                return users

        except FileNotFoundError:
            self.createLog()
            return self.listUsers()
