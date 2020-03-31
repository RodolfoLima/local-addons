{
    'name': 'Library Books',
    'summary': "Manage your books",
    'depends': ['base', 'decimal_precision'],
    'data': ['views/library_book.xml',
             'security/ir.model.access.csv',
             'security/library_security.xml'],
    'category': 'Library',
    'test': ['test/test_books.yml'],
}