from django.core.management.base import BaseCommand

from catalog.menu_addons import seed_menu_addons


class Command(BaseCommand):
    help = "Seed menu add-on groups from ADD ONS menu and link them to POS products."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-link",
            action="store_true",
            help="Create add-on groups only; do not link products.",
        )

    def handle(self, *args, **options):
        stats = seed_menu_addons(link_products=not options["no_link"])
        self.stdout.write(
            self.style.SUCCESS(
                "Menu add-ons: "
                f"{stats['groups_created']} groups created, "
                f"{stats['addons_created']} add-ons created, "
                f"{stats['links_created']} product links created."
            )
        )
