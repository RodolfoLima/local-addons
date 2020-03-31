# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.addons import decimal_precision as dp
from odoo.fields import Date as fDate
from datetime import timedelta as td
from datetime import date
from odoo import exceptions


class BaseArchive(models.AbstractModel):
    _name = 'base.archive'
    active = fields.Boolean(default=True)

    def do_archive(self):
        for record in self:
            record.active = not record.active


class LibraryBookLoan(models.Model):
    _name = 'library.book.loan'

    def _default_date(self):
        return fields.Date.today()

    book_id = fields.Many2one('library.book',
                              'Book', required=True)
    member_id = fields.Many2one('library.member',
                                'Borrower', required=True)
    state = fields.Selection([('ongoing', 'Ongoing'),
                              ('done', 'Done')], 'State',
                             default='ongoing', required=True)
    date = fields.Date('Loan date', required=True,
                       default=_default_date)

    duration = fields.Integer('Duration', default=15)
    date_due = fields.Date(
        compute='_compute_date_due',
        store=True,
        string='Due for'
    )

    @api.depends('date', 'date_due')
    def _compute_date_due(self):
        for loan in self:
            start_date = fields.Date.from_string(loan.date)
        due_date = start_date + td(days=loan.duration)
        loan.date_due = fields.Date.to_string(due_date)


class LibraryLoanWizard(models.TransientModel):
    _name = 'library.loan.wizard'
    member_id = fields.Many2one('library.member', string='Member')
    book_ids = fields.Many2many('library.book', string='Books')

    @api.multi
    def record_loans(self):
        for wizard in self:
            member = wizard.member_id
            books = wizard.book_ids
            loan = self.env['library.book.loan']
            for book in wizard.book_ids:
                values = self._prepare_loan(book)
                loan.create(values)

    @api.multi
    def _prepare_loan(self, book):
        return {'member_id': self.member_id.id,
                'book_id': book.id}


class LibraryLoanWizard(models.TransientModel):
    _inherit = 'library.loan.wizard'

    @api.multi
    def _prepare_loan(self, book):
        values = super(LibraryLoanWizard, self)._prepare_loan(book)
        loan_duration = self.member_id.loan_duration
        # today_str = fields.Date.context_today()
        today = date.today()
        expected = today + td(days=loan_duration)
        values.update(
            {'expected_return_date':
             fields.Date.to_string(expected)}
        )
        return values


class LibraryReturnsWizard(models.TransientModel):
    _name = 'library.returns.wizard'
    member_id = fields.Many2one('library.member', string='Member')
    book_ids = fields.Many2many('library.book', string='Books')

    @api.multi
    def record_returns(self):
        loan = self.env['library.book.loan']
        for rec in self:
            loans = loan.search(
                [('state', '=', 'ongoing'),
                    ('book_id', 'in', self.book_ids.ids),
                    ('member_id', '=', self.member_id.id)]
            )
            loans.write({'state': 'done'})

    @api.onchange('member_id')
    def onchange_member(self):
        loan = self.env['library.book.loan']
        loans = loan.search(
            [('state', '=', 'ongoing'),
             ('member_id', '=', self.member_id.id)]
        )
        self.book_ids = loans.mapped('book_id')


class LibraryBookLoan(models.Model):
    _inherit = 'library.book.loan'
    expected_return_date = fields.Date('Due for', required=True)


class LibraryBook(models.Model):
    _name = 'library.book'
    _inherit = ['base.archive']
    _description = 'Library Book'
    _order = 'date_release desc, name'
    _rec_name = 'short_name'

    manager_remarks = fields.Text('Manager Remarks')
    name = fields.Char('Title', required=True)
    isbn = fields.Char('ISBN')
    short_name = fields.Char('Short Title', required=True)
    date_release = fields.Date('Release Date')
    author_ids = fields.Many2many('res.partner', string='Authors')
    notes = fields.Text('Internal Notes')
    state = fields.Selection(
        [('draft', 'Unavailable'),
         ('available', 'Available'),
         ('borrowed', 'Borrowed'),
         ('lost', 'Lost')],
        'State')
    description = fields.Html('Description')
    cover = fields.Binary('Book Cover')
    out_of_print = fields.Boolean('Out of Print?')
    date_updated = fields.Datetime('Last Update')
    # pages = fields.Integer('Number of Pages')
    # Common attributes
    pages = fields.Integer(
        string='Number of pages',
        default=0,
        help='Total book page count',
        groups='base.group_user',
        states={'cancel': [('readonly', True)]},
        copy=True,
        index=False,
        readonly=False,
        required=False,
        company_dependent=False,
    )
    reader_rating = fields.Float(
        'Reader Average Rating',
        (14, 4),  # Optional precision (total, decimals)
    )
    cost_price = fields.Float('Book Cost', dp.get_precision('Book Price'))
    currency_id = fields.Many2one(
        'res.currency', string='Currency')
    retail_price = fields.Monetary(
        'Retail Price',
        # optional: currency_field='currency_id,
    )
    publisher_id = fields.Many2one(
        'res.partner', string='Publisher',
        # optional: ondelete='set null', context={}, domain=[],
    )
    publisher_city = fields.Char(
        'Publisher City', related='publisher_id.city',
        readonly=True)

    age_days = fields.Float(
        string='Days Since Release',
        compute='_compute_age',
        inverse='_inverse_age',
        search='_search_age',
        Store=False,
        compute_sudo=False,
    )

    _sql_constraints = [
        ('name_uniq',
         'UNIQUE (name)',
         'Book title must be unique.')
    ]

    @api.model
    def name_get(self):
        result = []
        for book in self:
            authors = book.author_ids.mapped('name')
            name = u'%s (%s)' % (book.name,
                                 u', '.join(authors))
            result.append((book.id, name))
        return result

    @api.model
    def _name_search(self, name='', args=None, operator='ilike',
                     limit=100, name_get_uid=None):
        args = [] if args is None else args.copy()
        # generates a new empty args if args is None, os makes a copy otherwise
        if not (name == '' and operator == 'ilike'):
            args += ['|', '|',
                     ('name', operator, name),
                     ('isbn', operator, name),
                     ('author_ids.name', operator, name)]
        return super(LibraryBook, self)._name_search(
            name='', args=args, operator='ilike',
            limit=limit, name_get_uid=name_get_uid)

    @api.constrains('date_release')
    def _check_release_date(self):
        for r in self:
            print(r.date_release)
            print(fields.Date.today())
            if r.date_release > fields.Date.today():
                raise models.ValidationError(
                    'Release date must be in the past')

    @api.depends('date_release')
    def _compute_age(self):
        today = fDate.from_string(fDate.today())
        for book in self.filtered('date_release'):
            delta = fDate.from_string(book.date_release - today)
            book.age_days = delta.days

    def _inverse_age(self):
        today = fDate.from_string(fDate.today())
        for book in self.filtered('date_release'):
            d = td(days=book.age_days) - today
            book.date_release = fDate.to_string(d)

    def _search_age(self, operator, value):
        today = fDate.from_string(fDate.today())
        value_days = td(days=value)
        value_date = fDate.to_string(today - value_days)
        return [('date_release', operator, value_date)]

    @api.model
    def _referencable_models(self):
        models = self.env['res.request.link'].search([])
        return [(x.object, x.name) for x in models]

    ref_doc_id = fields.Reference(
        selection='_referencable_models',
        string='Reference Document')

    @api.model
    def is_allowed_transition(self, old_state, new_state):
        allowed = [('draft', 'available'),
                   ('available', 'borrowed'),
                   ('borrowed', 'available'),
                   ('available', 'lost'),
                   ('borrowed', 'lost'),
                   ('lost', 'available')]
        return (old_state, new_state) in allowed

    @api.multi
    def change_state(self, new_state):
        for book in self:
            if book.is_allowed_transition(book.state, new_state):
                book.state = new_state
            else:
                continue

    @api.model
    def get_all_library_members(self):
        library_member_model = self.env['library.member']
        return library_member_model.search([])

    @api.model
    @api.returns('self', lambda rec: rec.id)
    def create(self, values):
        print(self.user_has_groups('my_module.group_library_user'))
        if not self.user_has_groups('my_module.group_library_manager'):
            if 'manager_remarks' in values:
                raise exceptions.UserError(
                    'You are not allowed to modify '
                    'manager_remarks create'
                )
        return super(LibraryBook, self).create(values)

    @api.multi
    def write(self, values):
        if not self.user_has_groups('my_module.group_library_manager'):
            if 'manager_remarks' in values:
                raise exceptions.UserError(
                    'You are not allowed to modify '
                    'manager_remarks'
                )
        return super(LibraryBook, self).write(values)

    """
    @api.model
    def fields_get(self,
                   allfields=None,
                   #write_access=True,
                   attributes=None):
        fields = super(LibraryBook, self).fields_get(
            allfields=allfields,
            #write_access=write_access,
            attributes=attributes
        )
        print(fields)
        if not self.user_has_groups('my_module.group_library_manager'):
            if 'manager_remarks' in fields:
                fields['manager_remarks']['readonly'] = True
    """


class ResPartner(models.Model):
    _inherit = 'res.partner'
    _order = 'name'
    published_book_ids = fields.One2many(
        'library.book', 'publisher_id',
        string='Published Books')
    authored_book_ids = fields.Many2many(
        'library.book', string='Authored Books')
    count_books = fields.Integer(
        'Number of Authored Books',
        compute='_compute_count_books'
    )

    @api.depends('authored_book_ids')
    def _compute_count_books(self):
        for r in self:
            r.count_books = len(r.authored_book_ids)


class LibraryMember(models.Model):
    _name = 'library.member'
    _inherits = {'res.partner': 'partner_id'}
    partner_id = fields.Many2one(
        'res.partner',
        ondelete='cascade')
    date_start = fields.Date('Member Since')
    date_end = fields.Date('Termination Date')
    member_number = fields.Char('Number')

    loan_duration = fields.Integer('Loan duration',
                                   default=10,
                                   required=True)

    @api.multi
    def borrow_books(self, book_ids):
        if len(self) != 1:
            raise exceptions.UserError(
                _('It is forbidden to loan the same books '
                  'to multiple members.')
            )
        loan_model = self.env['library.book.loan']
        for book in self.env['library.book'].browse(book_ids):
            val = self._prepare_loan(book)
            loan = loan_model.create(val)

    @api.multi
    def _prepare_loan(self, book):
        self.ensure_one()
        return {'book_id': book.id,
                'member_id': self.id,
                'duration': self.loan_duration}

    @api.onchange('date_end')
    def on_change_date_end(self):
        date_end = fields.Date.from_string(self.date_end)
        today = date.today()
        if date_end <= today:
            self.loan_duration = 0
            return {
                'warning': {
                    'title': 'expired membership',
                    'message': "Membership has expired",
                },
            }

    @api.multi
    def return_all_books(self):
        self.ensure_one()
        wizard = self.env['library.returns.wizard']
        values = {'member_id': self.id}
        specs = wizard._onchange_spec()
        updates = wizard.onchanges(values, ['member_id'], specs)
        values.update(updates.get('value', {}))
        record = wizard.create(values)

        """
        value = updates.get('value', {})
        for name, val in value.iteritems():
            if isinstance(val, tuple):
                value[name]=val[0]
        values.update(value)
        record = wizard.create(values)
        """

"""
class LibraryMember(models.Model):
    _inherit = 'library.member'
    loan_duration = fields.Integer('Loan duration',
                                   default=10,
                                   required=True)
"""

