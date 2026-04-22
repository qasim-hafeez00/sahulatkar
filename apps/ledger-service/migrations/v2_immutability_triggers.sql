-- SahulatKar Ledger Service - Immutability Triggers Migration
-- Classification: Production Hardening (P1)

-- Trigger function to prevent updates/deletes on journal entries
CREATE OR REPLACE FUNCTION prevent_journal_mutation()
RETURNS TRIGGER AS $$
BEGIN
    -- Allow updating reversed_by_id only
    IF (TG_OP = 'UPDATE') THEN
        IF (OLD.id = NEW.id AND 
            OLD.entry_number = NEW.entry_number AND
            OLD.entry_date = NEW.entry_date AND
            OLD.total_debit = NEW.total_debit AND
            OLD.total_credit = NEW.total_credit AND
            OLD.is_balanced = NEW.is_balanced) THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'Journal entries are immutable. Create a reversal instead.';
    ELSIF (TG_OP = 'DELETE') THEN
        RAISE EXCEPTION 'Journal entries cannot be deleted. Use soft-delete if absolutely necessary, but audit integrity requires persistence.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger function for lines (absolute immutability)
CREATE OR REPLACE FUNCTION prevent_line_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Journal entry lines are immutable.';
END;
$$ LANGUAGE plpgsql;

-- Apply triggers
DROP TRIGGER IF EXISTS trg_immutable_journal ON journal_entries;
CREATE TRIGGER trg_immutable_journal
BEFORE UPDATE OR DELETE ON journal_entries
FOR EACH ROW EXECUTE FUNCTION prevent_journal_mutation();

DROP TRIGGER IF EXISTS trg_immutable_lines ON journal_entry_lines;
CREATE TRIGGER trg_immutable_lines
BEFORE UPDATE OR DELETE ON journal_entry_lines
FOR EACH ROW EXECUTE FUNCTION prevent_line_mutation();

-- Add DB-level CHECK constraints for total balance
ALTER TABLE journal_entries ADD CONSTRAINT chk_balanced CHECK (total_debit = total_credit);
ALTER TABLE journal_entries ADD CONSTRAINT chk_nonzero CHECK (total_debit > 0);
