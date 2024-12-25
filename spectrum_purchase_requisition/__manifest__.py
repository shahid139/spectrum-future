# -*- coding: utf-8 -*-
{
    "name": "Purchase Requisition",
    "summary": "A Purchase Requisition is an internal document used to formally request the procurement of goods or services within an organization."
               "It serves as the first step in the purchasing process, ensuring that the requested items are reviewed, approved, and tracked before proceeding with procurement.",
    "author": "Shahid",
    "website": "www.spectrum.com",
    "category": "purchase,inventory,account,crm,project",
    "version": "0.1",
    "depends": ["base", 'sales_team', 'crm', 'mail','purchase','account'],
    # always loaded
    "data": [
        'security/ir.model.access.csv',

    ],


}