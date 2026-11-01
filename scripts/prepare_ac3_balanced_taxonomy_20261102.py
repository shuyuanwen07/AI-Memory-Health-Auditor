"""Prepare new, intentionally curated AC3 diagnostic cases; do not run a model.

These are controlled fault injections for evaluator validation. They are not
observed target-model answers, evidence of failure prevalence, or human labels.
Independent source/answer/category review must precede a frozen scoring trial.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "output/proposal-delivery/ac3-balanced-taxonomy-validation-20261102-v1"
SEED = 20261102


@dataclass(frozen=True)
class Scenario:
    domain: str
    title: str
    stable: str
    accuracy_question: str
    inaccurate_answer: str
    original: str
    update: str
    freshness_question: str
    stale_answer: str
    current_answer: str
    conflict_subject: str
    conflict_a: str
    conflict_b: str
    conflict_question: str
    default: str
    exception: str
    scope_question: str
    misused_default_answer: str
    appropriate_answer: str
    extra: str
    extra_question: str
    extra_answer: str


# Every row changes the actual task and evidence, rather than substituting
# names into one common question. Values are fictional and self-contained.
SCENARIOS = [
    Scenario(
        "Public-library display", "Aster Library weekend display",
        "Aster Library keeps its large-print catalogue in cabinet C.",
        "Where should a volunteer look for Aster Library's large-print catalogue?", "Look in cabinet F.",
        "The weekend display was originally due to open at 10 am.",
        "The librarian changed the display opening to 11 am. This replaces the original 10 am opening, which no longer applies.",
        "What opening time should go on the current weekend-display notice?", "The display opens at 10 am.", "The current opening is 11 am, replacing 10 am.",
        "the display's one final reading room", "Room Cedar", "Room Birch",
        "Can we name the display's final reading room from the current records?",
        "The library team normally prefers printed visitor handouts.",
        "For the Aster accessible tour only, the organiser requires a digital handout that works with a screen reader. The usual printed-handout preference remains in force for other tours.",
        "Prepare the visitor handout for the Aster accessible tour. Which format should we use?",
        "Use a printed handout, following the team's usual preference.",
        "Use a screen-reader-compatible digital handout for the accessible tour; printed handouts remain the default elsewhere.",
        "The spare visitor pencils are in a green tray.", "Which tray contains the spare visitor pencils?", "The green tray."),
    Scenario(
        "Community gardening", "Willow Garden seed evening",
        "Willow Garden stores its hand trowels in shed 4.",
        "A helper needs a hand trowel at Willow Garden. Which shed contains them?", "They are in shed 2.",
        "The seed-collection evening was first scheduled for Tuesday.",
        "The coordinator moved this seed-collection evening to Thursday and cancelled the Tuesday session. There is one session this week.",
        "On which day should volunteers now attend the seed-collection evening?", "Attend on Tuesday.", "Attend on Thursday; the Tuesday session was cancelled.",
        "the seed evening's one allocated planting plot", "Plot East", "Plot West",
        "Which planting plot can we treat as the settled allocation for this seed evening?",
        "Willow volunteers generally prefer morning field sessions.",
        "The Night Pollinators project requires its moth observation session after sunset. This project exception does not change the volunteers' morning preference for ordinary field sessions.",
        "Schedule the Night Pollinators moth observation. Should it follow the usual morning preference?",
        "Schedule it in the morning because that is the volunteers' preference.",
        "Schedule the moth observation after sunset, as the Night Pollinators project requires. The morning preference applies to ordinary sessions.",
        "The clean gloves are in the blue bin.", "Where are Willow Garden's clean gloves kept?", "In the blue bin."),
    Scenario(
        "Ceramics tuition", "Harbour Clay introductory course",
        "The Harbour Clay teaching kiln is electric.",
        "What type of kiln does Harbour Clay use for teaching?", "It uses a gas kiln.",
        "The introductory class originally lasted 90 minutes.",
        "The tutor lengthened the introductory class to 120 minutes. The 90-minute duration is superseded for this class.",
        "How long is the introductory class under the current timetable?", "It lasts 90 minutes.", "It now lasts 120 minutes, replacing the earlier 90-minute duration.",
        "the single finish for the demonstration glaze batch", "a matte finish", "a gloss finish",
        "What finish is settled for the demonstration batch, given the two active batch sheets?",
        "The studio normally prefers a short demonstration without written steps.",
        "For the First Pot beginners' course, the tutor requires a demonstration with a written step-by-step guide. Other courses keep the usual short-demonstration format.",
        "Prepare the demonstration for First Pot beginners. Which teaching format should we choose?",
        "Give only a short demonstration without written steps, as the studio usually prefers.",
        "Give the First Pot demonstration with a written step-by-step guide; its beginner-specific requirement applies.",
        "Loan aprons hang on hook 5.", "Which hook holds the loan aprons?", "Hook 5."),
    Scenario(
        "Amateur astronomy", "Orion Club public skywatch",
        "Orion Club stores the spare tripods in locker 7.",
        "Where are the spare tripods recorded as stored?", "They are in locker 3.",
        "The public skywatch was initially set to start at 8 pm.",
        "The organiser moved the start of this skywatch to 9 pm, replacing the 8 pm start. The earlier start is cancelled.",
        "What start time should be communicated for the skywatch now?", "Tell visitors it starts at 8 pm.", "Tell visitors it starts at 9 pm; 8 pm was replaced.",
        "the skywatch's one final viewing platform", "the north platform", "the south platform",
        "Which viewing platform is definitively assigned by the active skywatch records?",
        "Club members generally prefer full-colour printed star charts.",
        "For the Dark Sky session, the organiser requires a red-light tablet chart. The printed-chart preference still applies to the club's daytime displays.",
        "Select a chart for the Dark Sky observing session. Which option follows its requirement?",
        "Choose a full-colour printed chart because that is the club's preference.",
        "Choose the red-light tablet chart for Dark Sky. The printed-chart preference belongs to other activities.",
        "The spare lens caps are in a yellow case.", "Which case holds the spare lens caps?", "The yellow case."),
    Scenario(
        "Bicycle repair volunteering", "Pedal Shed repair stall",
        "Pedal Shed's labelled hex-key set has a 4 mm key.",
        "What size key is listed in Pedal Shed's labelled hex-key set?", "It is 6 mm.",
        "The stall volunteer sign-up originally closed on 12 June.",
        "The organiser extended sign-up for this stall to 16 June. The 12 June closing date is no longer valid.",
        "Which closing date applies to the stall's volunteer sign-up?", "Sign-up closes on 12 June.", "The current closing date is 16 June, superseding 12 June.",
        "the stall's one final inspection counter", "the left counter", "the right counter",
        "Can we state a final inspection counter from the stall's current allocation sheets?",
        "Pedal Shed normally prefers volunteer check-in by email.",
        "For the Street Wheels stall only, volunteers must check in using its QR ticket. Email remains the preference for ordinary indoor sessions.",
        "A Street Wheels volunteer is arriving. Which check-in method should we recommend?",
        "Recommend email check-in because that is Pedal Shed's normal preference.",
        "Recommend the QR ticket for Street Wheels; email is the default for ordinary indoor sessions.",
        "Repaired-bike tags for collection are orange.", "What colour identifies the collection tags?", "Orange."),
    Scenario(
        "Museum visitor materials", "Lantern Museum audio walk",
        "The Lantern Museum master audio files use WAV format.",
        "Which file format is recorded for the museum's master audio?", "The master files use MP3.",
        "The audio walk originally met at the south gate.",
        "The visitor lead changed this walk's meeting point to the north gate and withdrew the south-gate instruction.",
        "Where should audio-walk visitors meet under the latest instruction?", "Meet at the south gate.", "Meet at the north gate; the south-gate instruction was withdrawn.",
        "the one final direction of the walk's numbered gallery route", "ascending room numbers", "descending room numbers",
        "Which gallery-route direction has been settled by the active route sheets?",
        "The museum normally prefers a spoken introduction from a guide.",
        "Inside the Quiet Archive gallery, this walk requires a silent introduction using captions. Other galleries retain the spoken-introduction preference.",
        "Prepare the introduction inside Quiet Archive. How should it be delivered?",
        "Have the guide give a spoken introduction, following the usual museum preference.",
        "Use a silent captioned introduction inside Quiet Archive; spoken introductions remain suitable elsewhere.",
        "Audio-walk lanyards are stored in drawer L.", "Which drawer contains the audio-walk lanyards?", "Drawer L."),
    Scenario(
        "Board-game club administration", "Maple Games open evening",
        "Maple Games keeps its spare game pieces in cupboard 2.",
        "Which cupboard is listed for spare game pieces?", "Cupboard 8 holds them.",
        "The open-evening registration fee was initially 6 dollars.",
        "The committee replaced the 6-dollar fee with an 8-dollar fee for this open evening. The earlier fee no longer applies.",
        "What registration fee should be quoted for the open evening?", "Quote a 6-dollar registration fee.", "Quote 8 dollars; the former 6-dollar fee was replaced.",
        "the open evening's single final equipment checkout time", "6 pm", "7 pm",
        "What equipment checkout time is actually settled for the open evening?",
        "The club generally prefers players to reserve a place online.",
        "For the New Players table, the organiser requires walk-in registration at the table. Other tables keep the online-reservation preference.",
        "Advise someone joining the New Players table. Which registration approach applies?",
        "Tell them to reserve online because that is the club's general preference.",
        "Tell them to register as a walk-in at the New Players table. Online reservation remains the default for other tables.",
        "The loan score pads have green covers.", "What colour covers identify the loan score pads?", "Green covers."),
    Scenario(
        "Community music rehearsals", "Cedar Voices rehearsal",
        "Cedar Voices uses a digital piano in its practice room.",
        "What kind of piano is recorded in the practice room?", "The room has an upright acoustic piano.",
        "The rehearsal was originally scheduled for Tuesday.",
        "The music director moved this rehearsal to Wednesday and cancelled the Tuesday booking.",
        "Which day now applies to this rehearsal?", "It is scheduled for Tuesday.", "It is now Wednesday; Tuesday was cancelled.",
        "the one final key for the group's single concert arrangement", "F major", "G major",
        "Which key can be treated as final for this arrangement from the two active score approvals?",
        "The group generally prefers four-part harmony in its warm-ups.",
        "For the Welcome Singers induction, the director requires a unison warm-up. This exception leaves the four-part preference unchanged for regular rehearsals.",
        "Design the Welcome Singers induction warm-up. Should we use the normal harmony format?",
        "Use four-part harmony because it is the group's usual preference.",
        "Use a unison warm-up for Welcome Singers; four-part harmony remains the regular-rehearsal preference.",
        "The spare music folders are purple.", "What colour are the spare music folders?", "Purple."),
    Scenario(
        "Repair-cafe logistics", "Patch Cafe textile desk",
        "Patch Cafe labels its textile kits with a blue triangle.",
        "Which symbol identifies Patch Cafe's textile kits?", "A red circle identifies them.",
        "The textile desk was originally due to open at 1 pm.",
        "The coordinator changed this desk's opening to 2 pm. The 1 pm opening was explicitly cancelled.",
        "At what time should the current textile-desk notice say it opens?", "The desk opens at 1 pm.", "It opens at 2 pm, replacing the cancelled 1 pm opening.",
        "the one final typeface on this desk's event banner", "a serif typeface", "a sans-serif typeface",
        "Which banner typeface is settled by the two currently valid design sheets?",
        "The cafe normally prefers reusable cups at its indoor meetings.",
        "For the Mobile Repair van visit, the host requires the supplied sealed water bottles. Reusable cups remain the indoor-meeting preference.",
        "Pack drinks for the Mobile Repair van visit. Which containers should be selected?",
        "Pack reusable cups because the cafe normally prefers them.",
        "Select the supplied sealed water bottles for the van visit. Reusable cups remain the indoor default.",
        "The sign-in clipboard is kept at table 4.", "Which table holds the sign-in clipboard?", "Table 4."),
    Scenario(
        "Neighbourhood book exchange", "Birch Street book swap",
        "The book swap sorts its permanent shelf alphabetically by author.",
        "How is the permanent book-swap shelf sorted?", "It is sorted by book height.",
        "The donor form was originally due on 1 August.",
        "The organiser extended this donor form's deadline to 3 August. The 1 August deadline is superseded.",
        "What is the current deadline for submitting the donor form?", "Submit it by 1 August.", "Submit it by 3 August; the former 1 August deadline was superseded.",
        "the swap's single final public entrance", "the east entrance", "the west entrance",
        "Which public entrance has a settled final designation in the active swap instructions?",
        "The swap generally prefers to issue paper receipts.",
        "For the Remote Donor parcel service, receipts must be sent by email. The paper-receipt preference still applies to in-person donations.",
        "Issue a receipt for a Remote Donor parcel. Which method applies?",
        "Issue a paper receipt because that is the swap's usual preference.",
        "Send the Remote Donor receipt by email; paper receipts remain the in-person preference.",
        "Volunteer badges for the swap are blue.", "What colour are the volunteer badges?", "Blue."),
    Scenario(
        "Paddling-club administration", "Reed Club equipment collection",
        "Reed Club keeps its spare paddle straps in rack 2.",
        "Which rack holds the spare paddle straps?", "They are in rack 9.",
        "Equipment collection was initially set for 11 am.",
        "The organiser moved this equipment collection to noon, replacing the 11 am slot. The earlier slot is cancelled.",
        "What time should members now use for equipment collection?", "Use the 11 am collection slot.", "Use noon; the 11 am slot was cancelled.",
        "this collection's one final numbered pickup dock", "Dock 1", "Dock 2",
        "Can the final pickup dock be identified from the two active collection records?",
        "Reed Club generally prefers weekday administrative briefings.",
        "For the Weekend Welcome programme, the committee requires its administrative briefing on Saturday. The weekday preference remains for other programmes.",
        "Schedule Weekend Welcome's administrative briefing. Which day pattern should guide it?",
        "Schedule a weekday briefing because that is the club's general preference.",
        "Schedule the Weekend Welcome briefing on Saturday. The weekday preference applies to other programmes.",
        "Blank equipment labels are in a blue box.", "Which box contains blank equipment labels?", "The blue box."),
    Scenario(
        "Photography-club exhibition", "Silver Frame members' show",
        "Silver Frame's exhibition preview images are stored as PNG files.",
        "What file format does Silver Frame record for its exhibition previews?", "The previews are stored as TIFF files.",
        "Members could originally submit three photographs each.",
        "The curator increased the submission limit for this show to five photographs per member. The three-photograph limit is replaced.",
        "How many photographs may each member now submit to this show?", "Each member may submit three photographs.", "Each member may now submit five; the three-photo limit was replaced.",
        "the show's one final exhibition title", "Dawn", "Dusk",
        "Which exhibition title can be announced as final from the currently valid approvals?",
        "Silver Frame members generally prefer colour photographs for club displays.",
        "For the Monochrome Study wall, the curator requires black-and-white photographs only. Other display walls retain the colour preference.",
        "Choose a photograph for the Monochrome Study wall. Which treatment should it use?",
        "Choose a colour photograph because that is the club's general display preference.",
        "Choose a black-and-white photograph for Monochrome Study. Colour remains the preference on other walls.",
        "The exhibitors' name tags have grey backgrounds.", "What background colour is used on exhibitors' name tags?", "Grey."),
    Scenario(
        "Origami workshop", "Fold House public session",
        "Fold House's standard square paper measures 15 centimetres per side.",
        "What side length is recorded for Fold House's standard square paper?", "Each side measures 20 centimetres.",
        "The public session was originally 45 minutes long.",
        "The organiser extended this session to 60 minutes and withdrew the 45-minute duration.",
        "What duration should now appear for the public folding session?", "The session lasts 45 minutes.", "It now lasts 60 minutes; 45 minutes was withdrawn.",
        "the session's single final demonstration model", "a crane", "a frog",
        "Which demonstration model is settled in the two active lesson sheets?",
        "Fold House generally prefers advanced folding patterns.",
        "For the First Fold introduction, the teacher requires a simple beginner pattern. Advanced patterns remain the preference for the regular club.",
        "Choose a pattern for First Fold participants. Which difficulty should be used?",
        "Use an advanced pattern because Fold House normally prefers advanced folding.",
        "Use a simple beginner pattern for First Fold; the advanced-pattern preference is for the regular club.",
        "Finished display models go on stand 2.", "Which stand is designated for finished display models?", "Stand 2."),
    Scenario(
        "Social running-club registration", "Park Loop welcome run",
        "Park Loop's registration bibs are yellow.",
        "What colour bibs does Park Loop use for registration?", "The bibs are purple.",
        "Check-in for the welcome run was originally at 9 am.",
        "The coordinator brought this check-in forward to 8 am. The original 9 am check-in was cancelled.",
        "When should participants now check in for the welcome run?", "Check in at 9 am.", "Check in at 8 am; the 9 am instruction was cancelled.",
        "the welcome run's single final advertised route length", "5 kilometres", "7 kilometres",
        "What route length can be treated as final in the current welcome-run notices?",
        "Park Loop generally prefers text messages for event updates.",
        "For the Online Archive project, update notices must be emailed so they can be filed. Other projects keep the text-message preference.",
        "Send an update for Online Archive. Which communication channel should be chosen?",
        "Send a text message because that is Park Loop's usual preference.",
        "Email the Online Archive update so it can be filed; text messages remain the default for other projects.",
        "The reusable registration signs are stored in a flat case.", "What kind of case stores the reusable registration signs?", "A flat case."),
    Scenario(
        "Craft-fair planning", "Harbour Handmade fair",
        "The Harbour Handmade floor plan is printed on A3 paper.",
        "Which paper size is recorded for the fair's floor plan?", "The floor plan uses A5 paper.",
        "Stall setup was originally due to finish on Friday.",
        "The organiser moved this stall-setup deadline to Saturday. The Friday deadline has been replaced.",
        "On which day is stall setup now due to finish?", "Finish setup on Friday.", "Finish setup on Saturday; Friday was replaced.",
        "this exhibitor's one final numbered booth", "Booth 12", "Booth 14",
        "Which booth number is settled by the two live exhibitor allocation sheets?",
        "The exhibitor generally prefers cash payment at face-to-face stalls.",
        "For the Online Catalogue order service, the exhibitor requires card payment through its order page. Cash remains the face-to-face preference.",
        "Advise a customer ordering through Online Catalogue. Which payment method applies?",
        "Advise cash payment because the exhibitor usually prefers cash.",
        "Use card payment through the Online Catalogue order page; cash is the face-to-face preference.",
        "Packed display hooks use black labels.", "What colour labels identify the packed display hooks?", "Black labels."),
    Scenario(
        "Hobby robotics", "Gear Room demonstration",
        "Gear Room stores its demonstration wheels in cabinet Q.",
        "Where are Gear Room's demonstration wheels stored?", "They are in cabinet T.",
        "The demonstration programme was originally to use Python.",
        "The project lead replaced Python with Java for this demonstration programme. The Python instruction is cancelled for this programme.",
        "Which programming language is required for the current demonstration programme?", "Use Python.", "Use Java; Python was explicitly replaced for this programme.",
        "the one final distance unit displayed by this demonstration's screen", "metres", "centimetres",
        "Which distance unit is settled by the two active screen-configuration approvals?",
        "Gear Room generally prefers a wireless connection for demonstrations.",
        "For the Closed Bench demonstration, the project lead requires a cable connection. Other demonstrations keep the wireless preference.",
        "Set up the connection for Closed Bench. Which connection should be selected?",
        "Select wireless because that is Gear Room's normal demonstration preference.",
        "Select a cable connection for Closed Bench; wireless remains the preference elsewhere.",
        "Spare wheel clips are kept in case 3.", "Which case contains the spare wheel clips?", "Case 3."),
    Scenario(
        "Walking-club booking", "Ridge Walk leaflet session",
        "The Ridge Walk route leaflets are distributed as PDF files.",
        "What file format is recorded for the route leaflets?", "The route leaflets are DOCX files.",
        "Registration for the leaflet session originally closed on 5 July.",
        "The organiser extended this registration deadline to 8 July. The 5 July deadline no longer applies.",
        "Which registration deadline currently applies to the leaflet session?", "Registration closes on 5 July.", "Registration closes on 8 July; 5 July was superseded.",
        "this session's one final charter-bus departure time", "7 am", "8 am",
        "What departure time has a settled final status in the active charter records?",
        "The club generally prefers a short summary when presenting equipment lists.",
        "For the Equipment Archive project, the editor requires the full itemised equipment list. Other presentations keep the short-summary preference.",
        "Prepare the equipment-list page for Equipment Archive. Which level of detail is required?",
        "Provide a short summary because that is the club's normal preference.",
        "Provide the full itemised list for Equipment Archive; short summaries remain the preference elsewhere.",
        "Unclaimed leaflet packs are kept on shelf D.", "Which shelf holds unclaimed leaflet packs?", "Shelf D."),
    Scenario(
        "Makerspace printing", "Layer Lab exhibit order",
        "Layer Lab's demonstration spool is labelled PLA.",
        "Which material label appears on the demonstration spool?", "The spool is labelled ABS.",
        "The exhibit order was originally to be collected on Monday.",
        "The maker moved this order's collection to Thursday and cancelled Monday's collection slot.",
        "On which day should the exhibit order now be collected?", "Collect it on Monday.", "Collect it on Thursday; Monday's slot was cancelled.",
        "the one final orientation for this order's single display panel", "portrait", "landscape",
        "Which panel orientation is actually settled by the two valid order sheets?",
        "Layer Lab generally prefers a fast draft finish for demonstrations.",
        "For the Public Showcase order, the curator requires the detailed fine finish. Other demonstration orders keep the fast-draft preference.",
        "Select the finish for Public Showcase. Which setting should be used?",
        "Use the fast draft finish because that is Layer Lab's general demonstration preference.",
        "Use the detailed fine finish for Public Showcase; fast draft remains the default for other demonstrations.",
        "The print-order folder has a silver tab.", "What colour tab marks the print-order folder?", "A silver tab."),
    Scenario(
        "Amateur theatre", "River Stage matinee",
        "River Stage stores spare costume belts in chest F.",
        "Which chest contains River Stage's spare costume belts?", "They are stored in chest H.",
        "The matinee was first listed to begin at 2 pm.",
        "The producer moved this matinee to 3 pm, replacing the 2 pm start. The old start time is cancelled.",
        "What start time should now be shown on the matinee invitation?", "Show a 2 pm start.", "Show a 3 pm start; 2 pm was replaced.",
        "the one final lead credit on this production's single poster", "Morgan", "Riley",
        "Whose lead credit can we publish as final from the active poster approvals?",
        "The theatre generally prefers bright lighting for costume photographs.",
        "For the Shadow Study photo session, the designer requires dim silhouette lighting. The bright-lighting preference remains for ordinary costume photographs.",
        "Arrange the lighting for Shadow Study. Which treatment follows the session brief?",
        "Use bright lighting because that is the theatre's usual costume-photo preference.",
        "Use dim silhouette lighting for Shadow Study; bright lighting remains the ordinary costume-photo preference.",
        "The spare backdrop is indigo.", "What colour is the spare backdrop?", "Indigo."),
    Scenario(
        "Baking-club meetings", "Flour Circle recipe exchange",
        "Flour Circle's demonstration recipe lists 250 grams of flour.",
        "How much flour is listed in the demonstration recipe?", "The recipe lists 400 grams of flour.",
        "The recipe-exchange call was originally due to start at 10 am.",
        "The host rescheduled this call to 11 am and cancelled the 10 am start.",
        "When should members now join the recipe-exchange call?", "Join at 10 am.", "Join at 11 am; the 10 am start was cancelled.",
        "the one final orientation of this exchange's digital recipe card", "landscape", "portrait",
        "Which recipe-card orientation has been settled by the current layout approvals?",
        "Flour Circle generally prefers handwritten recipe cards.",
        "For the Searchable Catalogue project, the editor requires typed recipe text. Handwritten cards remain the preference for informal exchanges.",
        "Prepare a recipe for Searchable Catalogue. Which text format should we use?",
        "Use a handwritten card because that is Flour Circle's usual preference.",
        "Use typed recipe text for Searchable Catalogue; handwritten cards remain the informal-exchange preference.",
        "The demonstration measuring spoons have red handles.", "What colour handles identify the demonstration measuring spoons?", "Red handles."),
    Scenario(
        "Film discussion", "Frame Forum screening",
        "Frame Forum uses a 16:9 preview screen.",
        "Which aspect ratio is recorded for the preview screen?", "The preview screen is 4:3.",
        "The discussion after the screening was originally limited to 50 minutes.",
        "The host extended this discussion to 65 minutes. The earlier 50-minute limit is replaced.",
        "How long is the discussion allowed to run under the revised plan?", "It is limited to 50 minutes.", "It may run for 65 minutes; the 50-minute limit was replaced.",
        "the one final subtitle language in this screening's single release file", "Spanish", "French",
        "Which subtitle language can be treated as final from the two valid release approvals?",
        "Frame Forum generally prefers spoken debate after a film.",
        "For the Quiet Reflection screening, the facilitator requires silent written feedback. The spoken-debate preference remains for other screenings.",
        "Plan the feedback activity for Quiet Reflection. Which format applies?",
        "Hold a spoken debate because Frame Forum normally prefers debate.",
        "Use silent written feedback for Quiet Reflection; spoken debate remains the preference for other screenings.",
        "The spare projector remote is in locker 9.", "Which locker contains the spare projector remote?", "Locker 9."),
    Scenario(
        "Radio-club outreach administration", "Beacon Club visitor day",
        "Beacon Club's welcome placard has a blue border.",
        "What border colour is recorded for Beacon Club's welcome placard?", "The border is orange.",
        "Visitor-day registration initially allowed 12 places.",
        "The organiser increased this visitor day's capacity to 16 places, replacing the 12-place limit.",
        "What place limit now applies to visitor-day registration?", "The limit is 12 places.", "The current limit is 16 places; the 12-place limit was replaced.",
        "the one final typeface for this visitor day's badge sheet", "Arial", "Calibri",
        "Which badge-sheet typeface is settled by the two active print approvals?",
        "Club members generally prefer technical abbreviations in internal explanations.",
        "For the First Visit tour, the outreach lead requires plain-language explanations without technical abbreviations. Internal meetings keep the abbreviation preference.",
        "Prepare explanations for First Visit. Which language style should be chosen?",
        "Use technical abbreviations because the club generally prefers them.",
        "Use plain language without technical abbreviations for First Visit; abbreviations remain the internal-meeting preference.",
        "There are eight blank visitor clipboards.", "How many blank visitor clipboards are recorded?", "Eight."),
    Scenario(
        "Preserves exchange packaging", "Orchard Circle gift batch",
        "Orchard Circle's demonstration jars are hexagonal.",
        "What shape is recorded for the demonstration jars?", "They are cylindrical.",
        "Gift-batch labels were originally due to be handed over on 2 September.",
        "The packer moved this label handover to 4 September. The 2 September handover was cancelled.",
        "Which date should now be used for the gift-batch label handover?", "Use 2 September.", "Use 4 September; the 2 September handover was cancelled.",
        "the one final colour of every label in this uniform gift batch", "amber", "teal",
        "Which label colour is settled for the uniform batch from the two active packaging sheets?",
        "Orchard Circle generally prefers bulk packages for its exchange table.",
        "For the Single Gift order, the coordinator requires each jar to be packed individually. Bulk packaging remains the preference for the exchange table.",
        "Pack the Single Gift order. Which packaging approach should be followed?",
        "Use bulk packages because that is Orchard Circle's usual preference.",
        "Pack each jar individually for Single Gift; bulk packages remain the exchange-table preference.",
        "The spare gift-box ribbon is white.", "What colour is the spare gift-box ribbon?", "White."),
    Scenario(
        "Chess-club organisation", "Oak Knights analysis evening",
        "Oak Knights marks its loan chess boxes with brass tags.",
        "What kind of tags identify Oak Knights' loan boxes?", "They have plastic tags.",
        "The analysis evening was originally planned for five rounds.",
        "The organiser changed this evening's plan to seven rounds, replacing the five-round plan.",
        "How many rounds should the current analysis-evening plan show?", "Show five rounds.", "Show seven rounds; the five-round plan was replaced.",
        "the one final time-display format on this evening's single printed scoreboard", "12-hour format", "24-hour format",
        "Which scoreboard time format is settled by the two active printing instructions?",
        "The club generally prefers blitz games at casual meetings.",
        "For the Deep Analysis session, the organiser requires the classical time format. Casual meetings keep the blitz preference.",
        "Choose the game format for Deep Analysis. Which format should be selected?",
        "Select blitz because it is the club's normal preference.",
        "Select the classical format for Deep Analysis; blitz remains the casual-meeting preference.",
        "Spare bishops are kept in tray B.", "Which tray contains spare bishops?", "Tray B."),
    Scenario(
        "Language exchange", "Harbour Words practice call",
        "Harbour Words uses lined paper for its sign-in sheets.",
        "What kind of paper is recorded for the sign-in sheets?", "The sign-in sheets use graph paper.",
        "The practice call was first scheduled for 6 pm.",
        "The coordinator moved this practice call to 6:30 pm and cancelled the 6 pm start.",
        "At what time should members now join the practice call?", "Join at 6 pm.", "Join at 6:30 pm; the 6 pm start was cancelled.",
        "the one final name printed for this single exchange group", "Atlas", "Harbour",
        "Which exchange-group name is settled by the two valid name approvals?",
        "Harbour Words generally prefers free conversation during practice.",
        "For the Reception Practice exercise, the facilitator requires a scripted role-play. Other practice sessions keep the free-conversation preference.",
        "Plan Reception Practice. Which activity format should be used?",
        "Use free conversation because that is the group's general practice preference.",
        "Use a scripted role-play for Reception Practice; free conversation remains the preference for other sessions.",
        "The shared vocabulary cards are kept in pocket 5.", "Which pocket holds the shared vocabulary cards?", "Pocket 5."),
    Scenario(
        "Volunteer mapmaking", "Grid Guild brochure map",
        "Grid Guild's working map uses a 200-metre grid.",
        "What grid interval is recorded on the working map?", "It uses a 500-metre grid.",
        "The brochure-map export was originally due on 10 October.",
        "The editor extended this export deadline to 12 October. The 10 October deadline has been superseded.",
        "What export deadline currently applies to the brochure map?", "Export it by 10 October.", "Export it by 12 October; the earlier 10 October deadline was superseded.",
        "the one final orientation of this single brochure map", "north-up", "east-up",
        "Which orientation is settled by the two active brochure-map specifications?",
        "Grid Guild generally prefers detailed multi-layer maps for internal work.",
        "For the Easy Walk brochure, the editor requires a simple high-contrast map. Internal maps keep the detailed multi-layer preference.",
        "Prepare the map for Easy Walk. Which map style should be selected?",
        "Use a detailed multi-layer map because that is Grid Guild's normal preference.",
        "Use a simple high-contrast map for Easy Walk; detailed multi-layer maps remain the internal-work preference.",
        "The map-symbol master file uses SVG format.", "Which file format is recorded for the map-symbol master?", "SVG."),
    Scenario(
        "Seed exchange", "Glasshouse Circle label day",
        "Glasshouse Circle uses C6 envelopes for seed packets.",
        "Which envelope size is recorded for the seed packets?", "The packets use C5 envelopes.",
        "The label-day meeting was originally assigned to the old shed.",
        "The coordinator moved this meeting to the new glasshouse and cancelled the old-shed venue instruction.",
        "Where should participants now go for the label-day meeting?", "Go to the old shed.", "Go to the new glasshouse; the old-shed instruction was cancelled.",
        "the one final variety name on every label in this single seed batch", "Ridge Pea", "Valley Pea",
        "Which variety name is settled for this seed batch by the two active label approvals?",
        "Glasshouse Circle generally prefers Latin plant names on its labels.",
        "For the First Seeds beginner packs, the coordinator requires common plant names. Other packs keep the Latin-name preference.",
        "Write labels for First Seeds. Which naming style should be used?",
        "Use Latin plant names because that is the circle's usual label preference.",
        "Use common plant names for First Seeds; Latin names remain the preference for other packs.",
        "The packet-label ink is black.", "What colour ink is recorded for packet labels?", "Black ink."),
    Scenario(
        "Mobile games library", "Rolling Games field day",
        "Rolling Games' demonstration set contains six dice.",
        "How many dice are recorded in the demonstration set?", "There are four dice.",
        "The field-day loan was initially booked for two hours.",
        "The coordinator extended this loan to three hours, replacing the two-hour booking.",
        "How long may the current field-day loan last?", "The loan lasts two hours.", "It lasts three hours; the two-hour booking was replaced.",
        "the one final travel direction of the van's single pickup loop", "clockwise", "counterclockwise",
        "Which loop direction has a settled final designation in the active van schedules?",
        "Rolling Games generally prefers digital instruction manuals.",
        "For the Offline Field Day loan, the librarian requires printed manuals. Other loans keep the digital-manual preference.",
        "Prepare instructions for Offline Field Day. Which format should be packed?",
        "Pack digital manuals because Rolling Games normally prefers them.",
        "Pack printed manuals for Offline Field Day; digital manuals remain the preference for other loans.",
        "The spare counters are kept in an oak-pattern box.", "Which box contains the spare counters?", "The oak-pattern box."),
    Scenario(
        "Adult writing group", "Draft Circle anthology",
        "Draft Circle's shared manuscript binder is burgundy.",
        "What colour is recorded for the shared manuscript binder?", "It is turquoise.",
        "Anthology submissions were originally limited to 800 words.",
        "The editor increased this anthology's submission limit to 1,000 words and withdrew the 800-word limit.",
        "What word limit should current anthology contributors follow?", "Follow the 800-word limit.", "Follow the 1,000-word limit; the 800-word limit was withdrawn.",
        "the one final title of this single anthology", "Crossing", "Landing",
        "Which anthology title is settled by the two active editorial approvals?",
        "Draft Circle members generally prefer writing in rhyme.",
        "For the Short Prose anthology section, the editor requires prose submissions. Other group exercises keep the rhyme preference.",
        "Prepare a submission for Short Prose. Which writing form should be used?",
        "Write it in rhyme because that is the group's usual preference.",
        "Write prose for Short Prose; rhyme remains the preference for other exercises.",
        "Blank cover sheets are stored on shelf 6.", "Which shelf holds blank cover sheets?", "Shelf 6."),
    Scenario(
        "Instrument lending administration", "Note Bank collection desk",
        "Note Bank uses round stickers on its lending folders.",
        "What sticker shape identifies Note Bank's lending folders?", "The stickers are square.",
        "This instrument collection was first booked for Thursday.",
        "The librarian moved this collection to Friday and cancelled the Thursday booking.",
        "On which day should the borrower now collect the instrument?", "Collect it on Thursday.", "Collect it on Friday; Thursday's booking was cancelled.",
        "this collection's single final numbered service counter", "Counter 2", "Counter 3",
        "Which service counter is settled for this collection in the active desk records?",
        "Note Bank generally prefers phone calls for collection notices.",
        "For the Remote Loan service, the librarian requires an emailed collection notice. Other services keep the phone-call preference.",
        "Send the collection notice for Remote Loan. Which channel should be used?",
        "Phone the borrower because that is Note Bank's usual preference.",
        "Email the Remote Loan collection notice; phone calls remain the preference for other services.",
        "The empty folder dividers are grey.", "What colour are the empty folder dividers?", "Grey."),
]


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def main():
    assert len(SCENARIOS) == 30
    DEST.mkdir(parents=True, exist_ok=True)
    sources, items, key = [], [], []
    for index, s in enumerate(SCENARIOS, start=1):
        source_id = f"BTX-H{index:02d}"
        constraint = (
            f"For {s.title}, {s.conflict_subject} must have exactly one value for this one event or item. "
            "The two allocation records below have equal authority, are both still active, and were issued at the same time. "
            "Neither record has priority or supersedes the other. No later decision resolves their disagreement."
        )
        record_a = f"Active record R states that {s.conflict_subject} is {s.conflict_a}."
        record_b = f"Active record S states that {s.conflict_subject} is {s.conflict_b}."
        texts = [s.stable, s.original, s.update, constraint, record_a, record_b, s.default, s.exception, s.extra]
        day = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc) + timedelta(days=index * 4)
        messages = []
        for number, content in enumerate(texts, start=1):
            # Equal timestamps for R/S reinforce that source order is not priority.
            minute = 4 if number in (5, 6) else number - 1
            messages.append({"message_id": f"{source_id}-M{number:02d}", "role": "user", "content": content,
                             "timestamp": (day + timedelta(minutes=minute)).isoformat()})
        sources.append({"source_id": source_id, "history_id": source_id, "domain": s.domain,
                        "title": s.title, "messages": messages})

        conflict_expected = (
            f"The records do not establish a final choice. Record R says {s.conflict_a}; "
            f"record S says {s.conflict_b}. They have equal authority and no priority, so ask which record should govern."
        )
        # Each control uses the same source as its four failures. This supports
        # cluster-paired analysis; it is not five independent source histories.
        control_kind = (index - 1) % 4
        if control_kind == 0:
            control_question, control_answer, evidence = s.extra_question, s.extra_answer, [9]
            control_basis = "ordinary_fact"
        elif control_kind == 1:
            control_question = f"Summarise the superseded arrangement and the current replacement for {s.title}."
            control_answer, evidence = s.current_answer, [2, 3]
            control_basis = "explicit_update"
        elif control_kind == 2:
            control_question = f"A colleague wants a definite choice for {s.conflict_subject}. Explain what the records allow us to conclude and what remains to clarify."
            control_answer, evidence = conflict_expected, [4, 5, 6]
            control_basis = "unresolved_conflict"
        else:
            control_question = f"For the special activity in {s.title}, recommend the applicable option and distinguish it from the general preference."
            control_answer, evidence = s.appropriate_answer, [7, 8]
            control_basis = "scoped_exception"
        cases = [
            ("accuracy", s.accuracy_question, s.inaccurate_answer, False, "accuracy", [1], s.stable),
            ("freshness", s.freshness_question, s.stale_answer, False, "freshness", [2, 3], s.current_answer),
            ("conflict", s.conflict_question, f"Use {s.conflict_a} as the final choice.", False, "conflict_resolution", [4, 5, 6], conflict_expected),
            ("scope", s.scope_question, s.misused_default_answer, False, "appropriate_use", [7, 8], s.appropriate_answer),
            ("control", control_question, control_answer, True, None, evidence, control_answer),
        ]
        for kind, question, answer, passed, category, evidence, expected in cases:
            review_id = sha(f"{SEED}:{source_id}:{kind}".encode())[:24]
            items.append({"review_id": review_id, "source_id": source_id, "question": question,
                          "answer": answer, "response_origin": "curated_synthetic_diagnostic_answer"})
            key.append({"review_id": review_id, "source_id": source_id, "case_kind": kind,
                        "intended_verdict": "pass" if passed else "fail", "intended_failure_type": category,
                        "control_basis": control_basis if passed else None,
                        "source_evidence_ids": [f"{source_id}-M{number:02d}" for number in evidence],
                        "expected_behavior": expected,
                        "reference_status": "author_intention_only_independent_review_pending"})
    random.Random(SEED).shuffle(items)
    random.Random(SEED + 1).shuffle(sources)
    assert len(items) == len({x["review_id"] for x in items}) == 150
    assert len({x["question"] for x in items}) == 150
    source_lookup = {s["source_id"]: s for s in sources}
    assert len(source_lookup) == 30 and all(x["source_id"] in source_lookup for x in items)
    planned = Counter(x["intended_failure_type"] or "pass" for x in key)
    assert planned == {"accuracy": 30, "freshness": 30, "conflict_resolution": 30, "appropriate_use": 30, "pass": 30}
    data = {"format": "ac3-balanced-taxonomy-diagnostic-draft-v1", "version": 1,
            "created_date": "2026-11-02", "status": "draft_independent_review_pending_not_frozen",
            "provenance": {"source_origin": "fictional_synthetic_histories_curated_for_this_diagnostic",
                           "answer_origin": "intentionally_curated_fault_injections_and_correct_controls",
                           "observed_target_model_responses": False, "model_calls": 0,
                           "generator": str(Path(__file__).relative_to(ROOT)),
                           "generator_sha256": sha(Path(__file__).read_bytes()), "shuffle_seed": SEED},
            "history_count": 30, "answer_count": 150,
            "review_notice": "Judge actual source support and actual answer behaviour. Author intentions are private and are not reference labels. A correct answer or an uncertain verdict has no failure type. Multiple independent errors or inadequate category evidence must remain multiple/uncertain rather than be forced into a class.",
            "scope": "Controlled evaluator diagnosis only; not naturally occurring target performance, failure prevalence, a population sample, or a full external benchmark.",
            "sources": sources, "items": items}
    private = {"format": "ac3-balanced-taxonomy-private-author-intentions-v1", "version": 1,
               "status": "not_ground_truth_independent_review_pending", "private": True,
               "must_not_be_supplied_to_candidate_judges_or_independent_reviewers": True,
               "planned_counts_not_verified_labels": dict(planned), "items": key}
    write(DEST / "dataset-draft.json", data)
    write(DEST / "private-intended-key.json", private)
    audit = {"histories": 30, "source_messages": sum(len(s["messages"]) for s in sources),
             "unique_question_texts": 150, "answers": 150, "items_per_history": dict(Counter(x["source_id"] for x in items)),
             "duplicate_full_source_messages": sum(n - 1 for n in Counter(m["content"] for s in sources for m in s["messages"]).values() if n > 1),
             "planned_counts_not_verified_labels": dict(planned), "pass_control_bases": dict(Counter(x["control_basis"] for x in key if x["intended_verdict"] == "pass")),
             "dataset_sha256": sha((DEST / "dataset-draft.json").read_bytes()),
             "private_key_sha256": sha((DEST / "private-intended-key.json").read_bytes()),
             "human_review_complete": False, "independent_ai_review_complete": False}
    write(DEST / "preparation-integrity.json", audit)
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
