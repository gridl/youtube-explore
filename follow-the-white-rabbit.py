__author__ = 'Guillaume Chaslot'

import urllib2
import re
import json
import sys
import argparse

from bs4 import BeautifulSoup


RECOMMENDATIONS_PER_VIDEO = 1
RESULTS_PER_SEARCH = 1

# NUMBER OF LIKES ON A VIDEO
MATURITY_THRESHOLD = 10

class YoutubeFollower():
    def __init__(self, verbose=False, name='', alltime=True):
        # Name
        self._name = name
        self._alltime = alltime

        self._verbose = verbose;

        # Dict video_id to {'likes': ,
        #                   'dislikes': ,
        #                   'views': ,
        #                   'recommendations': []}
        self._video_infos = self.try_to_load_video_infos()

        # Dict search terms to [video_ids]
        self._search_infos = {}


    def clean_count(self, text_count):
        # Ignore non ascii
        ascii_count = text_count.encode('ascii', 'ignore')
        # Ignore non numbers
        p = re.compile('[\d,]+')
        return int(p.findall(ascii_count)[0])

    def get_search_results(self, search_terms, max_results):
        assert max_results < 20, 'max_results was not implemented to be > 20 in order to keep the code simpler'

        if self._verbose:
            print ('Searching for {}'.format(search_terms))

        # Trying to get results from cache
        if search_terms in self._search_infos and len(self._search_infos[search_terms]) >= max_results:
            return self._search_infos[search_terms][0:max_results]

        # Escaping search terms for youtube
        escaped_search_terms = urllib2.quote(search_terms.encode('utf-8'))

        # We only want search results that are videos, filtered by viewcoung.
        #  This is achieved by using the youtube URI parameter: sp=CAMSAhAB
        if self._alltime:
            filter = "CAMSAhAB"
        else:
            filter = "EgIQAQ%253D%253D"

        url = "https://www.youtube.com/results?sp=" + filter + "&q=" + escaped_search_terms

        html = urllib2.urlopen(url)
        soup = BeautifulSoup(html, "lxml")

        videos = []
        for item_section in soup.findAll('ol', {'class': 'item-section'}):
            for video_index in range(0, 20):
                video = item_section.contents[video_index * 2 + 1].li['data-video-ids']
                videos.append(video)

        self._search_infos[search_terms] = videos
        return videos[0:max_results]

    def get_recommendations(self, video_id, nb_recos_wanted):
        if video_id in self._video_infos:
            video = self._video_infos[video_id]
            recos_returned = []
            for reco in video['recommendations']:
                recos_returned.append(reco)
                if len(recos_returned) >= nb_recos_wanted:
                    return recos_returned[0:nb_recos_wanted]
                print ('Warning: ' + video_id + ' does not have enough recommendations: ' + repr(recos_returned))
                return recos_returned

        url = "https://www.youtube.com/watch?v=" + video_id
        html = urllib2.urlopen(url)
        soup = BeautifulSoup(html, "lxml")

        # Views
        views = -1
        for watch_count in soup.findAll('div', {'class': 'watch-view-count'}):
            try:
                views = self.clean_count(watch_count.contents[0])
            except IndexError:
                pass

        # Likes
        likes = -1
        for like_count in soup.findAll('button', {'class': 'like-button-renderer-like-button'}):
            try:
                likes = self.clean_count(like_count.contents[0].text)
            except IndexError:
                pass

        # Dislikes
        dislikes = -1
        for like_count in soup.findAll('button', {'class': 'like-button-renderer-dislike-button'}):
            try:
                dislikes = self.clean_count(like_count.contents[0].text)
            except IndexError:
                pass

        # Recommendations
        recos = []
        upnext = True
        for video_list in soup.findAll('ul', {'class': 'video-list'}):
            if upnext:
                # Up Next recommendation
                recos.append(video_list.contents[1].contents[1].contents[1]['href'].replace('/watch?v=', ''))
                upnext = False
            else:
                # 19 Otherss
                for i in range(1, 20):
                    try:
                        recos.append(video_list.contents[i].contents[1].contents[1]['href'].replace('/watch?v=', ''))
                    except IndexError:
                        if self._verbose:
                            print ('Could not get a recommendation because there are not enough')
                    except AttributeError:
                        if self._verbose:
                            print ('Could not get a recommendation because of malformed content')

        for eow_title in soup.findAll('span', {'id': 'eow-title'}):
            title = eow_title.text.strip()

        self._video_infos[video_id] = {'views': views,
                                       'likes': likes,
                                       'dislikes': dislikes,
                                       'recommendations': recos,
                                       'title': title}

        print repr(self._video_infos[video_id])
        return recos[0:nb_recos_wanted]

    def get_n_recommendations(self, seed, branching, depth):
        if depth is 0:
            return [seed]
        current_video = seed
        all_recos = []
        for video in self.get_recommendations(current_video, branching):
            all_recos.extend(self.get_n_recommendations(video, branching, depth -1))
        return all_recos

    def compute_all_recommendations_from_search(self, search_terms, search_results, branching, depth):
        search_results = self.get_search_results(search_terms, search_results)
        all_recos = []
        for video in search_results:
            all_recos.extend(self.get_n_recommendations(video, branching, depth))
            print 'One search result done'
        return all_recos

    def count(self, iterator):
        counts = {}
        for video in iterator:
            counts[video] = counts.get(video, 0) + 1
        return counts

    def go_deeper_from(self, search_term, search_results, branching, depth):
        all_recos = self.compute_all_recommendations_from_search(search_term, search_results, branching, depth)
        counts = self.count(all_recos)
        print '\n\n\nSearch term = ' + search_term + '\n'
        sorted_videos = sorted(counts,  key=counts.get, reverse=True)
        for video in sorted_videos:
            print str(counts[video]) + ' https://www.youtube.com/watch?v=' + video

    def save_video_infos(self):
        print 'Wrote file:'
        print '../data/video-infos-' + self._name + '.json'
        with open('../data/video-infos-' + self._name + '.json', 'w') as fp:
            json.dump(self._video_infos, fp)

    def try_to_load_video_infos(self):
        try:
            with open('../data/video-infos-' + self._name + '.json', 'r') as fp:
                return json.load(fp)
        except Exception as e:
            print 'Failed to load from graph ' + repr(e)
            return {}

    def count_recommendation_links(self):
        counts = {}
        for video_id in self._video_infos:
            for reco in self._video_infos[video_id]['recommendations']:
                counts[reco] = counts.get(reco, 0) + 1
        return counts

    def video_is_mature(self, video):
        return int(video['likes']) > MATURITY_THRESHOLD

    def print_graph(self, links_per_video, only_mature_videos=True):
        input_links_counts = self.count_recommendation_links()
        graph = {}
        nodes = []
        links = []
        for video_id in self._video_infos:
            video = self._video_infos[video_id]
            if video['likes'] < MATURITY_THRESHOLD:
                popularity = -1
            else:
                popularity = video['likes'] / float(video['likes'] + video['dislikes'] + 1)

            if self.video_is_mature(video):
                nodes.append({'id': video_id, 'size': input_links_counts.get(video_id, 0), 'popularity': popularity, 'type': 'circle', 'likes': video['likes'], 'dislikes': video['dislikes'], 'views': video['views']})
            link = 0
            for reco in self._video_infos[video_id]['recommendations']:
                if reco in self._video_infos:
                    if self.video_is_mature(self._video_infos[video_id]) and self.video_is_mature(self._video_infos[reco]):
                        links.append({'source': video_id, 'target': reco, 'value': 1})
                    link += 1
                    if link >= links_per_video:
                        break
        graph['nodes'] = nodes
        graph['links'] = links
        with open('./graph-' + self._name + '.json', 'w') as fp:
            json.dump(graph, fp)
        print 'Wrote graph as: ' + 'graph-' + self._name + '.json'

def main():
    global parser
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', help='Name under which the results will be stored')
    parser.add_argument('--query', help='The start search query')
    parser.add_argument('--searches', default='1', type=int, help='The number of search results to start the exploration')
    parser.add_argument('--branch', default='3', type=int, help='The branching factor of the exploration')
    parser.add_argument('--depth', default='5', type=int, help='The depth of the exploration')
    parser.add_argument('--alltime', default=False, type=bool, help='If we get results by highest number of views')
    args = parser.parse_args()

    if args.alltime:
        print repr(args.alltime)


    yf = YoutubeFollower(verbose=True, name=args.name, alltime=args.alltime)
    yf.go_deeper_from(args.query,
                      search_results=args.searches,
                      branching=args.branch,
                      depth=args.depth)
    yf.save_video_infos()
    return 0

if __name__ == "__main__":
    sys.exit(main())
