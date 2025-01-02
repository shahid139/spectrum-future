{
    'name': 'Custom Purchase Order Report',
    'version': '1.0',
    'category': 'Purchases',
    'summary': 'Custom Purchase Order Report Template',
    'description': 'Adds a custom design for Purchase Order reports.',
    'author': 'Your Name',
    'depends': ['purchase', 'web'],
    'data': [
        'views/purchase_order_report.xml',
        'views/purchase_order_report_action.xml',
    ],
    'installable': True,
    'application': False,
}
