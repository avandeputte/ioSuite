# Demo data

To show the suite to someone, or to try it before your own data goes in, a new suite can be filled with a made-up
family of four, the Calloways, with something in every app. Everything in it is invented: the people, their address,
the businesses, the email addresses (`example.com`), the phone numbers (555-01xx, kept for fiction), the
accounts and the amounts. The photos in ioPix and ioRecipe are real pictures from Wikimedia Commons and StockSnap,
under Creative Commons or public domain licenses (credited with them); the people in ioPix's photos are stock models
whose made-up names became the Calloways.

The demo data is a package of its own in the program folder, which nothing loads until the demo is turned on (see
*Where it lives* below).

## Who is in it

| Account | Who | Role |
| --- | --- | --- |
| `morgan` | Morgan Calloway, a landscape architect | suite admin |
| `riley` | Riley Calloway, a science teacher | admin of every app |
| `ava` | Ava, 14 | member |
| `theo` | Theo, 9 | member |

They all sign in with the password `calloway`. The four are in the family list (Settings › People › Family), each
with a colour, linked to their card in ioContact and their face in ioPix.

## What each app gets

- **ioStart**: shared bookmark folders (Family, School, Home) and each person's own.
- **ioCalendar**: the week's routine (piano, soccer, swimming, movie night) from five weeks ago, outings, school
  events, a work calendar for each parent, the children's own, the public holidays (United States, Oregon) and the
  birthdays from ioContact.
- **ioTask**: the Family, Groceries and House lists, everyone's Personal list, repeating chores, subtasks.
- **ioContact**: the four, grandparents, an uncle, friends, the school, the dentist, the vet; relations set, so the
  family tree and the birthdays show.
- **ioPix**: about 200 photos of family days (Christmas, Easter, a picnic, a birthday, the lake house) and trips
  (Iceland, Santorini, Yosemite, Kyoto, the Swiss Alps, ...), with dates, places, people's faces, keywords and
  captions; a download of about 80 MB. Without internet: some drawn pictures instead.
- **ioNote**: each person's own notes, in folders, with tags.
- **ioRecipe**: eight family recipes (real, cookable ones) with a photo of each dish, two cookbooks, Ava's own,
  favourites and ratings.
- **ioThings**: the house's rooms, appliances, electronics, the car, receipts, warranties, upkeep and its log.
- **ioMoney**: checking, savings, a card, investments, the house and the car with their loans, six months of
  transactions, recurring payments and the net worth over time.
- **ioDocs**: everyone's passports (with scans that read back), two driver's licenses (front and the barcode on the
  back), birth and marriage certificates, the home and car insurance, the car's registration, health cards and the wills.
- **ioHealth**: three months of steps, heart rate, sleep, weight, activity rings and workouts (with routes) for each.
- **ioDNS** and **ioBackup**: example names, servers and jobs, all turned off, so nothing is synced or run.

The dates follow the day the demo is made: the events are this week and the next, the health data ends yesterday.

## Turning it on

**Docker**: tick *Fill it with demo data* in the [Docker Compose builder](https://iosuite.iothing.net/compose/). The
container turns the demo on before it serves, and every app fills itself at its first start (the four accounts come
with the first one). It is only done for a new suite: a stack whose suite has accounts of its own besides the
admin's is left alone.

**An installed server** (Proxmox, Linux, Mac):

```sh
iosuite demo
systemctl restart 'iosuite*'
```

turns the demo on; each app adds its share as it starts (the four accounts come with the first one). An app added
later adds its own at its first start too, until `iosuite demo --off`, which stops that and removes nothing.

The demo data is added once per app, and it is meant for a suite that starts with it: the easiest way out is to start
over (on Docker, with an empty data folder). Deleting the four accounts under Settings › People › People removes
each one's own data in every app, but what the family shares (the Family calendar and lists, the household's
accounts, the things, the family recipes) stays, as it would for a real person. ioPix adds demo photos only when it
keeps its own library, in a folder `Calloway family (demo)` of the photos folder: a digiKam library is never added to.

## Where it lives

The demo data is the `iosuite_demo` package of the program folder: the family and one seed per app, written with that
app's own code. No app imports it; an app that starts while the demo is on, and has not added its share yet, runs its
seed from it. ioPix's photos are a download of their own (`iopix-demo-photos.zip`, about 80 MB, with `CREDITS.md`
among them), fetched when ioPix adds its share; without internet it draws some pictures instead.
