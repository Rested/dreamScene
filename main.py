import subprocess
import nltk
import glob
import pydub
from pydub import AudioSegment
from pydub.silence import split_on_silence
import praw
import youtube_dl
import time
from random import randint
from pyo import *


def generate_audio(description, voice, wpm):
    subprocess.call(["say",
                     "-f", "descriptions/%s.txt" % description,
                     "-o", "readings/%s.aiff" % description,
                     "-v", voice,
                     "-r", str(wpm)])
    subprocess.call(["ffmpeg",
                    "-y",
                    "-i", "readings/%s.aiff" % description,
                    "-f", "mp3",
                    "-acodec", "libmp3lame",
                    "-ab", "192000",
                    "-ar", "44100",
                    "readings/%s.mp3" % description])


def get_nouns(tokenized_text):
    nouns = []
    for word in nltk.pos_tag(tokenized_text):
        if word[1] == "NN" or word[1] == "NNS":
            nouns.append(word[0])
    return nouns


def find_sfx(words):
    sfx = {}
    for word in words:
        #TODO: make words louder where the sentence contains two+ words in the sfx description, quiter else
        sfx[word] = glob.glob("sfx/*/*/*%s*.wav" % word.capitalize())
        sfx[word] += glob.glob("sfx/*/*/*%s*.wav" % word)
        sfx[word] += glob.glob("sfx/*/*%s*/*.wav" % word.capitalize())
        sfx[word] += glob.glob("sfx/*/*%s*/*.wav" % word)
    return sfx


def add_sfx_to_reading(word_chunks, tokenized_text, nouns, sfx, silence_length, reading):
    pos = 0
    overlays = {}
    for i in range(0, len(word_chunks)):
        print "%d of %d done slicing audio" % (i, len(word_chunks))
        if tokenized_text[i] in nouns:
            for sound in sfx[tokenized_text[i]]:
                if sound in overlays:
                    overlays[sound].append(pos)
                else:
                    overlays[sound] = [pos]

        pos += len(word_chunks[i]) + silence_length
    i = 0
    for sound in overlays:
        i+=1
        sf = AudioSegment.from_wav(sound)[:8000]
        sf -= 20
        sf = sf.fade_out(1000).fade_in(1000)
        print "Adding %s to reading in %d places - sound %d of %d" % (sound, len(overlays[sound]), i, len(overlays))
        for t in overlays[sound]:
            reading = reading.overlay(sf, position=t)

    return reading


def get_ambient(min_length, nouns, description):
    user_agent = "Ambient Getter by /u/restdy"
    r = praw.Reddit(user_agent=user_agent)
    the_track = ""
    for noun in nouns[-15:-1]:
        submissions = r.search(noun, subreddit='ambientmusic')
        for item in submissions:
            if "www.youtube.com" in item.url or "youtu.be" in item.url:
                if the_track == "":
                    the_track = item
                elif the_track.score < item.score:
                    the_track = item
    cmd = ("youtube-dl -o %s %s" % ("ambient/%s" % description, the_track.url)).split(" ")
    print cmd
    subprocess.call(cmd)
    subprocess.call(["ffmpeg",
                    "-y",
                    "-i", glob.glob("ambient/%s*" % description)[0],
                    "-f", "mp3",
                    "-acodec", "libmp3lame",
                    "-ab", "192000",
                    "-ar", "44100",
                    "ambient/%s.mp3" % description])

     # TODO: Only get videos/collection of videos over min_length
    time.sleep(10)
    return AudioSegment.from_mp3("/Users/restd/PycharmProjects/dreamScene/ambient/%s.mp3" % description)


def process_reading(filename, lng):
    s = Server(audio='offline')
    s.boot()

    s.recordOptions(dur=lng/1000, filename=filename.replace(".aiff", ".wav"), fileformat=1, sampletype=0)
    print filename
    a = SfPlayer(filename, loop=False, mul=.4)
    #lf = Sine(freq=.001, mul=800, add=1000)
    b = Freeverb(a, size=[.79, .8], damp=.9, bal=.3)
    f = Tone(b, 200).mix(2)#.out()
    pva = PVAnal(f, size=1024, overlaps=4, wintype=2)
    #pvs = PVAddSynth(pva, pitch=1, num=100, first=0, inc=1).out()
    #pva = PVAnal(f, size=2048)
    t = ExpTable([(0, 1), (61, 1), (71, 0), (131, 1), (171, 0), (511, 0)], size=512)
    pvf = PVFilter(pva, t)
    pvg = PVGate(pvf, thresh=-110, damp=0)

    pvv = PVVerb(pvg, revtime=0.4, damp=0.3)

    pvs = PVSynth(pvv).mix(2).out()
    #s.stop()
    s.start()
    # cleanup
    # TODO: Make this sound nice and work
    s.shutdown()



def main():
    voice = "Kate"
    description = "fern_hill"
    silence_length = 145
    words_per_minute = 140 #maybe this should be slower
    #TODO: maybe make it so the ambient is same bpm as wpm
    print "Doing text-to-speech synthesis."
    generate_audio(description, voice, words_per_minute)

    print "Getting nouns"
    with open("descriptions/%s.txt" % description, "r") as f:
        text = f.read()
        text = text.decode('utf-8')
    tokenizer = nltk.RegexpTokenizer(r'\w+')
    tokenized_text = tokenizer.tokenize(text)
    nouns = get_nouns(tokenized_text)

    print "Getting sfx for nouns"
    sfx = find_sfx(nouns)


    try:
        reading = AudioSegment.from_file("/Users/restd/PycharmProjects/dreamScene/readings/%s.wav" % description, format="wav") + 19
    except IOError:
        reading1 = AudioSegment.from_file("/Users/restd/PycharmProjects/dreamScene/readings/%s.mp3" % description,
                                          format="mp3")
        process_reading("/Users/restd/PycharmProjects/dreamScene/readings/%s.aiff" % description, len(reading1))
        sys.exit(0)


    #TODO: make this less of a guessing game
    word_chunks = split_on_silence(reading, min_silence_len=silence_length, silence_thresh=-16)

    print "Adding sfx to reading"
    scene = add_sfx_to_reading(word_chunks, tokenized_text, nouns, sfx, silence_length, reading)

    print "Getting and adding related (rough) ambient music."
    ambient = get_ambient(len(scene), nouns, description)#len(scene), nouns)

    scene = scene.overlay(ambient - 16, loop=True)
    scene.export("scenes/%s.mp3" % description, format="mp3")
    # #TODO: experiment with overlaying multiple different voices
    # #TODO: experiment with poems with multiple voices in them like under milkwood


if __name__ == '__main__':
    main()