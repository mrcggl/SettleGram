import spacy
from spacy.matcher import Matcher
from typing import DefaultDict
from collections import defaultdict

# SET UP NLP Processing
nlp = spacy.load("it_core_news_sm")
matcher = Matcher(nlp.vocab)

add_expense = [{"LEMMA": {"IN": ["pay", "spend", "buy"]}, "POS": "VERB"}]
nuova_spesa = [{'LEMMA': {'IN': ['spesare', 'pagare', 'spendere', 'comprare']}, 'POS': 'VERB'}]
disable_member = [{"LEMMA": {"IN": ["disable", "remove", "deactivate"]}}]
enable_member = [{"LEMMA": {"IN": ["aggiungere", "attivare"]}}]
# Type of phrases: show me balance, show me status, print status, generate status
get_balance = [{"LEMMA": "balance"}]
get_payments = [{"LEMMA": "payments"}]
close_group = [{"LEMMA": "close"}]
open_group = [{"LEMMA": "open"}]


def remove_member_from_group(doc):
    for token in doc:
        if token.dep_ == 'nsubj':
            return token.text

def add_member_to_group(doc):
    for ent in doc.ents:
        print(ent.label_)

    for token in doc:
        print(token.text, token.dep_, token.pos_)
        if token.dep_ == 'nsubj' or token.pos_ == 'PROPN':
            return token.text

def build_expense_from_msg(doc) -> DefaultDict:
    expense_matcher = Matcher(nlp.vocab)
    payer_pattern = [{"POS": "PROPN", "DEP": "nsubj"}]
    amount_paid_pattern = [{"ENT_TYPE": "MONEY"}]
    purpose_pattern = [
        {"POS": "ADP"},
        {"POS": "DET", "OP": "?"},
        {"POS": "NOUN"}]
    for_whom_pattern = [
        {"LEMMA": {"IN": ["share", "split", "divide"]}, "POS": "VERB"},
        {"POS": "ADP"}]

    expense_matcher.add("payer", None, payer_pattern)
    expense_matcher.add("amount_paid", None, amount_paid_pattern)
    expense_matcher.add("purpose", None, purpose_pattern)
    expense_matcher.add("for_whom", None, for_whom_pattern)

    matches = expense_matcher(doc)
    expense = defaultdict()

    for match_id, start, end in matches:
        string_id = nlp.vocab.strings[match_id]
        if string_id == 'payer':
            expense['who_paid'] = doc[start:end][0].text
        if string_id == 'amount_paid':
            token = doc[start:end][0]
            print(token)
            if token.is_currency or token.text in {'euros', 'dollars', 'euro', 'dollari'}:
                expense['currency'] = token.text
            else:
                expense['amount'] = float(token.text)

        if string_id == 'purpose':
            expense['purpose'] = doc[end - 1:end][0].text
        if string_id == 'for_whom':
            for_whom = []
            for token in doc[end:]:
                if token.pos_ == "PROPN":
                    for_whom.append(token.text)
                elif token.pos_ == "PRON":
                    for_whom.append(token.text)
            expense['for_whom'] = for_whom
    return expense

def crea_nuova_spesa(doc):
    nuova_spesa = [{'LEMMA': {'IN': ['spesare', 'pagare', 'spendere', 'comprare']}, 'POS': 'VERB'}]
    divisione = [{'LEMMA': {'IN': ['dividere', 'condividere', 'compartire', 'spartire']}}]

    matcher.add('spesa', None, nuova_spesa)
    matcher.add('divisione', None, divisione)
    matches = matcher(doc)
    expense = {}
    expense['for_whom'] = []
    for match_id, start, end in matches:
        string_id = nlp.vocab.strings[match_id]
        if string_id == 'spesa':
            for token in doc[start:end]:
                if token.dep_ == 'ROOT':
                    # Get Amount
                    for child in token.head.children:
                        if child.dep_ == 'obj':
                            expense['currency'] = 'euro' if child.is_currency else child.text
                            head = child
                            for child in head.children:
                                if child.dep_ in {'nummod', 'amod'}:
                                    expense['amount'] = float(str(child.text).replace(',', '.'))
                        if child.dep_ == 'nsubj':
                            expense['who_paid'] = child.text
                        if child.dep_ == 'obl':
                            expense['purpose'] = child.text

                if doc[0].text.lower() == 'ho':
                    expense['who_paid'] = 'MSG_SENDER'
        elif string_id == 'divisione':
            # Pathway tutti
            for token in doc[start:]:
                if token.dep_ == 'case' and token.head.text == 'tutti':
                    expense['for_whom'].append(token.head.text)
        # Pathway nome
        if not expense['for_whom']:
            for ent in doc[end:].ents:
                expense['for_whom'].append(ent.text)

    # Pathway lui/lei
    for token in doc:
        if token.dep_ == 'case' and token.head.text in {'lui', 'lei', 'me'}:
            expense['for_whom'].append(expense['who_paid'])

    return expense