"""Family members on events: an event on the Family calendar (or any calendar) can be tagged with the people of the
family it is for ("Emma's swimming", "Dad's dentist").

The family is the suite's one list (iosuite_shared.family, Settings › People › Family for suite admins), less the
accounts with no role in ioCalendar: the same people, colours and initials as in every app. Only a member of the family
gets a private calendar of their own here. A tag is kept in the event
itself as an iCalendar CATEGORIES value with the member's display name, so calendar apps (Apple Calendar, Thunderbird,
DAVx5...) show it, and a category typed there with a member's name (or account name, in any case) tags the event here
too. The other categories of an event stay as they are.

How that is done is the suite's (iosuite_shared.family.Tags: ioTask tags its tasks the same way); what is this app's
is whose accounts count: those with a role here.
"""
from iosuite_shared.family import Tags

from iocalendar import users

tags = Tags(users)  # this app's family, kept for half a minute (tags.ttl)
in_family, family, forget, of, ids_of = tags.in_family, tags.family, tags.forget, tags.of, tags.ids_of
find, resolve, fold, public = tags.find, tags.resolve, tags.fold, tags.public
