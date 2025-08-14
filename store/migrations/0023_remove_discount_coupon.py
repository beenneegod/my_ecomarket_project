from django.db import migrations

def remove_discount_coupon_fields(apps, schema_editor):
    # Удаление полей discount/coupon из Order, если они есть
    with schema_editor.connection.cursor() as cursor:
        try:
            cursor.execute('ALTER TABLE store_order DROP COLUMN IF EXISTS discount CASCADE;')
        except Exception:
            pass
        try:
            cursor.execute('ALTER TABLE store_order DROP COLUMN IF EXISTS coupon_id CASCADE;')
        except Exception:
            pass

class Migration(migrations.Migration):
    dependencies = [
        ('store', '0018_alter_order_options_alter_orderitem_options_and_more'),
    ]
    operations = [
        migrations.RunPython(remove_discount_coupon_fields),
    ]
